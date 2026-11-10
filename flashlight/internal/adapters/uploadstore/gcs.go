package uploadstore

import (
	"context"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net/http"
	"time"

	"cloud.google.com/go/storage"
	"google.golang.org/api/googleapi"

	"github.com/Amund211/flashlight/internal/app"
)

type GCSStore struct {
	bucket *storage.BucketHandle
	signer string
}

// NewGCSStore signs as signer, or as the service account of the
// credentials when it is empty. The signer needs iam.serviceAccounts.signBlob
// on itself unless the credentials hold a private key.
func NewGCSStore(client *storage.Client, bucket, signer string) *GCSStore {
	return &GCSStore{bucket: client.Bucket(bucket), signer: signer}
}

func (s *GCSStore) SignPost(path, contentType string, size int64, expires time.Time) (app.UploadPostTarget, error) {
	policy, err := s.bucket.GenerateSignedPostPolicyV4(path, &storage.PostPolicyV4Options{
		GoogleAccessID: s.signer,
		Expires:        expires,
		Fields: &storage.PolicyV4Fields{
			ContentType:         contentType,
			StatusCodeOnSuccess: http.StatusNoContent,
		},
		Conditions: []storage.PostPolicyV4Condition{
			storage.ConditionContentLengthRange(uint64(size), uint64(size)),
		},
	})
	if err != nil {
		return app.UploadPostTarget{}, fmt.Errorf("failed to sign post for %s: %w", path, err)
	}
	return app.UploadPostTarget{URL: policy.URL, Fields: policy.Fields}, nil
}

func (s *GCSStore) Put(ctx context.Context, path, contentType string, data []byte) error {
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	w := s.bucket.Object(path).If(storage.Conditions{DoesNotExist: true}).NewWriter(ctx)
	w.ContentType = contentType
	w.ChunkSize = 0
	if _, err := w.Write(data); err != nil {
		cancel()
		_ = w.Close()
		return fmt.Errorf("failed to write %s: %w", path, err)
	}
	if err := w.Close(); err != nil {
		if hasStatus(err, http.StatusPreconditionFailed) {
			return fmt.Errorf("%s: %w", path, app.ErrUploadObjectExists)
		}
		return fmt.Errorf("failed to finish %s: %w", path, err)
	}
	return nil
}

func hasStatus(err error, code int) bool {
	var apiErr *googleapi.Error
	return errors.As(err, &apiErr) && apiErr.Code == code
}

func isNotFound(err error) bool {
	return errors.Is(err, storage.ErrObjectNotExist) || hasStatus(err, http.StatusNotFound)
}

func notFound(path string, err error) error {
	if isNotFound(err) {
		return fmt.Errorf("%s: %w", path, app.ErrUploadObjectNotFound)
	}
	return fmt.Errorf("failed to read %s: %w", path, err)
}

// A generation that was there at Stat and is gone now was replaced.
func changed(path string, err error) error {
	if isNotFound(err) {
		return fmt.Errorf("%s: %w", path, app.ErrUploadObjectChanged)
	}
	return fmt.Errorf("failed to read %s: %w", path, err)
}

func (s *GCSStore) Get(ctx context.Context, path string) ([]byte, error) {
	r, err := s.bucket.Object(path).NewReader(ctx)
	if err != nil {
		return nil, notFound(path, err)
	}
	defer func() { _ = r.Close() }()
	data, err := io.ReadAll(r)
	if err != nil {
		return nil, fmt.Errorf("failed to read %s: %w", path, err)
	}
	return data, nil
}

func (s *GCSStore) Stat(ctx context.Context, path string) (app.UploadObject, error) {
	attrs, err := s.bucket.Object(path).Attrs(ctx)
	if err != nil {
		return app.UploadObject{}, notFound(path, err)
	}
	return app.UploadObject{Bytes: attrs.Size, Generation: attrs.Generation, MD5: hex.EncodeToString(attrs.MD5)}, nil
}

func (s *GCSStore) ReadHead(ctx context.Context, path string, generation int64, n int64) ([]byte, error) {
	r, err := s.bucket.Object(path).Generation(generation).NewRangeReader(ctx, 0, n)
	if err != nil {
		return nil, changed(path, err)
	}
	defer func() { _ = r.Close() }()
	data, err := io.ReadAll(r)
	if err != nil {
		return nil, fmt.Errorf("failed to read %s: %w", path, err)
	}
	return data, nil
}

func (s *GCSStore) Copy(ctx context.Context, src string, generation int64, dst string) error {
	copier := s.bucket.Object(dst).CopierFrom(s.bucket.Object(src).Generation(generation))
	if _, err := copier.Run(ctx); err != nil {
		if isNotFound(err) {
			return fmt.Errorf("%s: %w", src, app.ErrUploadObjectChanged)
		}
		return fmt.Errorf("failed to copy %s to %s: %w", src, dst, err)
	}
	return nil
}

func (s *GCSStore) Delete(ctx context.Context, path string) error {
	err := s.bucket.Object(path).Delete(ctx)
	if err != nil && !errors.Is(err, storage.ErrObjectNotExist) {
		return fmt.Errorf("failed to delete %s: %w", path, err)
	}
	return nil
}
