package app

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"path"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/google/uuid"

	"github.com/Amund211/flashlight/internal/domain"
)

// ErrUploadNotFound is returned for an upload that does not exist, is done,
// or belongs to someone else.
var ErrUploadNotFound = errors.New("upload not found")

// ErrUploadIncomplete is returned when a file is not posted yet, or was
// posted again during the check. The upload is kept, so complete can be
// called again.
var ErrUploadIncomplete = errors.New("upload is not complete")

var (
	ErrUploadObjectNotFound = errors.New("object not found")
	ErrUploadObjectExists   = errors.New("object already exists")
	// ErrUploadObjectChanged is returned when the object is no longer at the
	// requested generation.
	ErrUploadObjectChanged = errors.New("object changed")
)

const uploadPostTTL = 15 * time.Minute

type UploadPostTarget struct {
	URL    string            `json:"url"`
	Fields map[string]string `json:"fields"`
}

type UploadObject struct {
	Bytes      int64
	Generation int64
	MD5        string
}

type UploadStore interface {
	// SignPost lets a client POST exactly one file of the given size and
	// content type to path until expires.
	SignPost(path, contentType string, size int64, expires time.Time) (UploadPostTarget, error)
	// Put fails with ErrUploadObjectExists if path exists.
	Put(ctx context.Context, path, contentType string, data []byte) error
	Get(ctx context.Context, path string) ([]byte, error)
	Stat(ctx context.Context, path string) (UploadObject, error)
	// ReadHead and Copy fail with ErrUploadObjectChanged if the object is no
	// longer at generation.
	ReadHead(ctx context.Context, path string, generation int64, n int64) ([]byte, error)
	Copy(ctx context.Context, src string, generation int64, dst string) error
	Delete(ctx context.Context, path string) error
}

type StartUploadFile struct {
	Name  string
	Bytes int64
}

type StartUploadRequest struct {
	Kind           string
	ConsentVersion string
	Fields         map[string]string
	Files          []StartUploadFile
	Identity       domain.UploadIdentity
	Client         domain.UploadClient
}

type StartedUpload struct {
	UploadID  string
	ExpiresAt time.Time
	// Files has one target per requested file, in order.
	Files []UploadPostTarget
}

// pendingUpload is stored by StartUpload and read back by CompleteUpload.
type pendingUpload struct {
	Meta  domain.UploadMeta `json:"meta"`
	Files []StartUploadFile `json:"files"`
}

type StartUpload func(ctx context.Context, req StartUploadRequest) (StartedUpload, error)

type CompleteUpload func(ctx context.Context, kind, uploadID string, identity domain.UploadIdentity) (string, error)

func pendingPrefix(kind domain.UploadKind, uploadID string) string {
	return path.Join(string(kind), "pending", uploadID) + "/"
}

func pendingFilePath(kind domain.UploadKind, uploadID string, i int) string {
	return fmt.Sprintf("%s%d.png", pendingPrefix(kind, uploadID), i)
}

func BuildStartUpload(store UploadStore, newID func() string, nowFunc func() time.Time) StartUpload {
	return func(ctx context.Context, req StartUploadRequest) (StartedUpload, error) {
		spec, err := domain.UploadKindSpecFor(req.Kind)
		if err != nil {
			return StartedUpload{}, err
		}
		fields, err := spec.ValidateFields(req.Fields)
		if err != nil {
			return StartedUpload{}, err
		}
		if _, err := time.Parse(time.DateOnly, req.ConsentVersion); err != nil {
			return StartedUpload{}, fmt.Errorf("%w: consentVersion is missing or invalid", domain.ErrInvalidUpload)
		}
		if !req.Identity.Type.IsKnown() || req.Identity.Key == "" {
			return StartedUpload{}, fmt.Errorf("%w: sign-in required", domain.ErrInvalidUpload)
		}
		if len(req.Files) == 0 {
			return StartedUpload{}, fmt.Errorf("%w: no files", domain.ErrInvalidUpload)
		}
		if len(req.Files) > spec.MaxFiles {
			return StartedUpload{}, fmt.Errorf("%w: more than %d files", domain.ErrInvalidUpload, spec.MaxFiles)
		}

		files := make([]StartUploadFile, len(req.Files))
		var total int64
		for i, file := range req.Files {
			name := cleanOriginalName(file.Name)
			if file.Bytes <= 0 {
				return StartedUpload{}, fmt.Errorf("%s: %w: file is empty", name, domain.ErrInvalidUpload)
			}
			if file.Bytes > spec.MaxFileBytes {
				return StartedUpload{}, fmt.Errorf("%s: %w: file is larger than %d MB", name, domain.ErrUploadTooLarge, spec.MaxFileBytes>>20)
			}
			total += file.Bytes
			files[i] = StartUploadFile{Name: name, Bytes: file.Bytes}
		}
		if total > spec.MaxTotalBytes {
			return StartedUpload{}, fmt.Errorf("%w: files are larger than %d MB in total", domain.ErrUploadTooLarge, spec.MaxTotalBytes>>20)
		}

		now := nowFunc().UTC()
		id := newID()
		pending := pendingUpload{
			Meta: domain.UploadMeta{
				UploadID:       id,
				Kind:           spec.Kind,
				SchemaVersion:  1,
				StartedAt:      now,
				ConsentVersion: req.ConsentVersion,
				Provenance:     domain.UploadProvenanceUserSubmitted,
				Verified:       false,
				Identity:       req.Identity,
				Client:         req.Client,
				Files:          []domain.UploadedFile{},
				UserReported:   fields,
			},
			Files: files,
		}
		data, err := json.Marshal(pending)
		if err != nil {
			return StartedUpload{}, fmt.Errorf("failed to marshal pending upload: %w", err)
		}
		if err := store.Put(ctx, pendingPrefix(spec.Kind, id)+"upload.json", "application/json", data); err != nil {
			return StartedUpload{}, fmt.Errorf("failed to store pending upload: %w", err)
		}

		expires := now.Add(uploadPostTTL)
		targets := make([]UploadPostTarget, len(files))
		for i, file := range files {
			target, err := store.SignPost(pendingFilePath(spec.Kind, id, i), "image/png", file.Bytes, expires)
			if err != nil {
				return StartedUpload{}, fmt.Errorf("failed to sign upload: %w", err)
			}
			targets[i] = target
		}

		return StartedUpload{UploadID: id, ExpiresAt: expires, Files: targets}, nil
	}
}

func BuildCompleteUpload(store UploadStore, nowFunc func() time.Time) CompleteUpload {
	return func(ctx context.Context, kind, uploadID string, identity domain.UploadIdentity) (string, error) {
		spec, err := domain.UploadKindSpecFor(kind)
		if err != nil {
			return "", ErrUploadNotFound
		}
		if parsed, err := uuid.Parse(uploadID); err != nil || parsed.String() != uploadID {
			return "", ErrUploadNotFound
		}

		prefix := pendingPrefix(spec.Kind, uploadID)
		data, err := store.Get(ctx, prefix+"upload.json")
		if errors.Is(err, ErrUploadObjectNotFound) {
			return "", ErrUploadNotFound
		}
		if err != nil {
			return "", fmt.Errorf("failed to read pending upload: %w", err)
		}
		var pending pendingUpload
		if err := json.Unmarshal(data, &pending); err != nil {
			return "", fmt.Errorf("failed to parse pending upload: %w", err)
		}
		if pending.Meta.Identity != identity {
			return "", ErrUploadNotFound
		}

		pendingPaths := []string{prefix + "upload.json"}
		for i := range pending.Files {
			pendingPaths = append(pendingPaths, pendingFilePath(spec.Kind, uploadID, i))
		}
		// Best effort, and also after the client is gone: the bucket's
		// lifecycle rule removes what is left.
		deletePending := func() {
			cleanupCtx := context.WithoutCancel(ctx)
			for _, p := range pendingPaths {
				_ = store.Delete(cleanupCtx, p)
			}
		}

		meta := pending.Meta
		meta.CompletedAt = nowFunc().UTC()
		stamp := meta.StartedAt.Format("2006-01-02T150405Z")
		inbox := path.Join(string(spec.Kind), "inbox", meta.StartedAt.Format(time.DateOnly), stamp+"_"+uploadID) + "/"
		metaPath := inbox + "meta.json"

		// An earlier complete wrote meta.json but failed to clean up.
		_, err = store.Stat(ctx, metaPath)
		if err == nil {
			deletePending()
			return uploadID, nil
		}
		if !errors.Is(err, ErrUploadObjectNotFound) {
			return "", fmt.Errorf("failed to check meta.json: %w", err)
		}

		generations := make([]int64, len(pending.Files))
		for i, file := range pending.Files {
			src := pendingFilePath(spec.Kind, uploadID, i)
			uploaded, info, err := checkUploadedFile(ctx, store, src, file.Bytes)
			if err != nil {
				if errors.Is(err, domain.ErrInvalidUpload) {
					deletePending()
				}
				return "", fmt.Errorf("%s: %w", file.Name, err)
			}
			generations[i] = uploaded.Generation
			meta.Files = append(meta.Files, domain.UploadedFile{
				Name:         fmt.Sprintf("%s_%s_%02d.png", stamp, uploadID[:8], i+1),
				OriginalName: file.Name,
				Bytes:        uploaded.Bytes,
				MD5:          uploaded.MD5,
				Width:        info.Width,
				Height:       info.Height,
				ColorType:    info.ColorType,
				BitDepth:     info.BitDepth,
			})
		}

		for i, file := range meta.Files {
			// Pinned to the generation we checked, in case the client posted again.
			err := store.Copy(ctx, pendingFilePath(spec.Kind, uploadID, i), generations[i], inbox+file.Name)
			if errors.Is(err, ErrUploadObjectChanged) {
				return "", fmt.Errorf("%s: %w: file changed during the check", pending.Files[i].Name, ErrUploadIncomplete)
			}
			if err != nil {
				return "", fmt.Errorf("failed to move %s: %w", file.Name, err)
			}
		}

		metaData, err := json.MarshalIndent(meta, "", "  ")
		if err != nil {
			return "", fmt.Errorf("failed to marshal upload meta: %w", err)
		}
		// Exists: a concurrent complete finished first.
		err = store.Put(ctx, metaPath, "application/json", metaData)
		if err != nil && !errors.Is(err, ErrUploadObjectExists) {
			return "", fmt.Errorf("failed to store meta.json: %w", err)
		}

		deletePending()
		return uploadID, nil
	}
}

func checkUploadedFile(ctx context.Context, store UploadStore, p string, wantBytes int64) (UploadObject, domain.PNGInfo, error) {
	uploaded, err := store.Stat(ctx, p)
	if errors.Is(err, ErrUploadObjectNotFound) {
		return UploadObject{}, domain.PNGInfo{}, fmt.Errorf("%w: file was not uploaded", ErrUploadIncomplete)
	}
	if err != nil {
		return UploadObject{}, domain.PNGInfo{}, fmt.Errorf("failed to stat %s: %w", p, err)
	}
	// The signed policy already enforces this.
	if uploaded.Bytes != wantBytes {
		return UploadObject{}, domain.PNGInfo{}, fmt.Errorf("%w: file size does not match", domain.ErrInvalidUpload)
	}
	head, err := store.ReadHead(ctx, p, uploaded.Generation, domain.PNGHeaderLen)
	if errors.Is(err, ErrUploadObjectChanged) {
		return UploadObject{}, domain.PNGInfo{}, fmt.Errorf("%w: file changed during the check", ErrUploadIncomplete)
	}
	if err != nil {
		return UploadObject{}, domain.PNGInfo{}, fmt.Errorf("failed to read %s: %w", p, err)
	}
	info, err := domain.ParsePNGHeader(head)
	if err != nil {
		return UploadObject{}, domain.PNGInfo{}, err
	}
	return uploaded, info, nil
}

const maxOriginalNameChars = 200

// cleanOriginalName keeps only the base name. It is stored for reference and
// never used in a path.
func cleanOriginalName(name string) string {
	if i := strings.LastIndexAny(name, `/\`); i >= 0 {
		name = name[i+1:]
	}
	if !utf8.ValidString(name) {
		return ""
	}
	if utf8.RuneCountInString(name) > maxOriginalNameChars {
		name = string([]rune(name)[:maxOriginalNameChars])
	}
	return name
}
