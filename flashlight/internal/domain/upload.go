package domain

import (
	"bytes"
	"encoding/binary"
	"errors"
	"fmt"
	"hash/crc32"
	"regexp"
	"slices"
	"strings"
	"time"
	"unicode/utf8"
)

// ErrInvalidUpload wraps every rejection of user input. Its message is shown
// to the user, so keep the wrapped reasons short and free of internals.
var ErrInvalidUpload = errors.New("invalid upload")
var ErrUploadTooLarge = errors.New("upload too large")

type UploadKind string

const UploadKindTabcap UploadKind = "tabcap"

type UploadKindSpec struct {
	Kind          UploadKind
	MaxFiles      int
	MaxFileBytes  int64
	MaxTotalBytes int64
	// ValidateFields returns the fields to store: trimmed, without empty
	// optional values.
	ValidateFields func(map[string]string) (map[string]string, error)
}

var uploadKinds = map[UploadKind]UploadKindSpec{
	UploadKindTabcap: {
		Kind:           UploadKindTabcap,
		MaxFiles:       30,
		MaxFileBytes:   10 << 20,
		MaxTotalBytes:  200 << 20,
		ValidateFields: validateTabcapFields,
	},
}

func UploadKindSpecFor(kind string) (UploadKindSpec, error) {
	spec, ok := uploadKinds[UploadKind(kind)]
	if !ok {
		return UploadKindSpec{}, fmt.Errorf("%w: unknown kind", ErrInvalidUpload)
	}
	return spec, nil
}

// UploadedFile describes a stored file. All of it is computed by us.
type UploadedFile struct {
	Name         string `json:"name"`
	OriginalName string `json:"originalName"`
	Bytes        int64  `json:"bytes"`
	MD5          string `json:"md5"`
	Width        int    `json:"width"`
	Height       int    `json:"height"`
	ColorType    string `json:"colorType"`
	BitDepth     int    `json:"bitDepth"`
}

type UploadIdentity struct {
	Type AuthSessionIdentityType `json:"type"`
	Key  string                  `json:"key"`
}

type UploadClient struct {
	Type    string `json:"type"`
	Version string `json:"version"`
}

// UploadMeta is written as meta.json next to the files. UserReported is
// user input that we only check for form, never for truth.
type UploadMeta struct {
	UploadID       string            `json:"uploadId"`
	Kind           UploadKind        `json:"kind"`
	SchemaVersion  int               `json:"schemaVersion"`
	StartedAt      time.Time         `json:"startedAt"`
	CompletedAt    time.Time         `json:"completedAt"`
	ConsentVersion string            `json:"consentVersion"`
	Provenance     string            `json:"provenance"`
	Verified       bool              `json:"verified"`
	Identity       UploadIdentity    `json:"identity"`
	Client         UploadClient      `json:"client"`
	Files          []UploadedFile    `json:"files"`
	UserReported   map[string]string `json:"userReported"`
}

const UploadProvenanceUserSubmitted = "user-submitted"

type fieldRule struct {
	required bool
	maxChars int
	enum     []string
	pattern  *regexp.Regexp
	// otherOf names the enum field this free-text field belongs to. It is
	// required when that field is "other", and forbidden otherwise.
	otherOf string
}

var versionPattern = regexp.MustCompile(`^\d+(\.\d+){1,2}$`)

var tabcapFieldRules = map[string]fieldRule{
	"launcher": {required: true, enum: []string{
		"official", "lunar", "badlion", "feather", "labymod",
		"prism-launcher", "multimc", "curseforge", "modrinth", "other",
	}},
	"launcherOther":  {maxChars: 100, otherOf: "launcher"},
	"mcVersion":      {required: true, enum: []string{"1.8.9", "1.12.2", "1.20.x", "1.21.x", "26.1.x", "other"}},
	"mcVersionOther": {maxChars: 20, pattern: versionPattern, otherOf: "mcVersion"},
	"resourcePack":   {maxChars: 200},
	"guiScale":       {enum: []string{"auto", "1", "2", "3", "4", "5", "6"}},
	"contact":        {maxChars: 100},
	"note":           {maxChars: 1000},
}

func validateTabcapFields(in map[string]string) (map[string]string, error) {
	return validateFields(tabcapFieldRules, in)
}

func validateFields(rules map[string]fieldRule, in map[string]string) (map[string]string, error) {
	invalid := func(name, reason string) (map[string]string, error) {
		return nil, fmt.Errorf("%w: %s %s", ErrInvalidUpload, name, reason)
	}

	out := make(map[string]string, len(in))
	for name, raw := range in {
		rule, ok := rules[name]
		if !ok {
			return invalid(name, "is not a known field")
		}
		if !utf8.ValidString(raw) {
			return invalid(name, "is not valid text")
		}
		value := strings.TrimSpace(raw)
		if value == "" {
			continue
		}
		if rule.maxChars > 0 && utf8.RuneCountInString(value) > rule.maxChars {
			return invalid(name, fmt.Sprintf("is longer than %d characters", rule.maxChars))
		}
		if rule.enum != nil && !slices.Contains(rule.enum, value) {
			return invalid(name, "has an unknown value")
		}
		if rule.pattern != nil && !rule.pattern.MatchString(value) {
			return invalid(name, "has the wrong format")
		}
		out[name] = value
	}

	for name, rule := range rules {
		_, present := out[name]
		if rule.otherOf != "" {
			wantPresent := out[rule.otherOf] == "other"
			if wantPresent && !present {
				return invalid(name, "is required")
			}
			if !wantPresent && present {
				return invalid(name, fmt.Sprintf("is only allowed when %s is other", rule.otherOf))
			}
			continue
		}
		if rule.required && !present {
			return invalid(name, "is required")
		}
	}

	return out, nil
}

// PNGHeaderLen is the signature and the IHDR chunk: length, type, data, crc.
const PNGHeaderLen = 8 + 4 + 4 + 13 + 4

const pngMaxSide = 8192

var pngSignature = []byte("\x89PNG\r\n\x1a\n")

type PNGInfo struct {
	Width     int
	Height    int
	BitDepth  int
	ColorType string
}

// ParsePNGHeader checks the first PNGHeaderLen bytes of a file. It accepts
// only RGB/RGBA, the formats Minecraft saves.
func ParsePNGHeader(h []byte) (PNGInfo, error) {
	notPNG := fmt.Errorf("%w: file is not a PNG", ErrInvalidUpload)
	if len(h) < PNGHeaderLen || !bytes.Equal(h[:8], pngSignature) {
		return PNGInfo{}, notPNG
	}
	if binary.BigEndian.Uint32(h[8:12]) != 13 || string(h[12:16]) != "IHDR" {
		return PNGInfo{}, notPNG
	}
	if crc32.ChecksumIEEE(h[12:29]) != binary.BigEndian.Uint32(h[29:33]) {
		return PNGInfo{}, notPNG
	}

	width := binary.BigEndian.Uint32(h[16:20])
	height := binary.BigEndian.Uint32(h[20:24])
	if width == 0 || height == 0 || width > pngMaxSide || height > pngMaxSide {
		return PNGInfo{}, fmt.Errorf("%w: image size is not supported", ErrInvalidUpload)
	}

	notOriginal := fmt.Errorf("%w: image is not an original screenshot", ErrInvalidUpload)
	var colorType string
	switch h[25] {
	case 2:
		colorType = "rgb"
	case 6:
		colorType = "rgba"
	default:
		return PNGInfo{}, notOriginal
	}
	bitDepth := h[24]
	if bitDepth != 8 && bitDepth != 16 {
		return PNGInfo{}, notOriginal
	}

	return PNGInfo{
		Width:     int(width),
		Height:    int(height),
		BitDepth:  int(bitDepth),
		ColorType: colorType,
	}, nil
}
