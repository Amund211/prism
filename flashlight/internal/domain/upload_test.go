package domain_test

import (
	"bytes"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/domaintest"
)

func validTabcapFields() map[string]string {
	return map[string]string{
		"launcher":     "lunar",
		"mcVersion":    "1.8.9",
		"resourcePack": "Default",
		"guiScale":     "auto",
	}
}

func TestUploadKindFromString(t *testing.T) {
	t.Parallel()

	spec, err := domain.UploadKindSpecFor("tabcap")
	require.NoError(t, err)
	require.Equal(t, domain.UploadKindTabcap, spec.Kind)
	require.Equal(t, 30, spec.MaxFiles)
	require.Equal(t, int64(10<<20), spec.MaxFileBytes)
	require.Equal(t, int64(200<<20), spec.MaxTotalBytes)

	for _, kind := range []string{"", "Tabcap", "debuglog", "../tabcap"} {
		_, err := domain.UploadKindSpecFor(kind)
		require.ErrorIs(t, err, domain.ErrInvalidUpload, kind)
	}
}

func TestValidateTabcapFields(t *testing.T) {
	t.Parallel()

	spec, err := domain.UploadKindSpecFor("tabcap")
	require.NoError(t, err)

	t.Run("valid", func(t *testing.T) {
		t.Parallel()
		fields, err := spec.ValidateFields(validTabcapFields())
		require.NoError(t, err)
		require.Equal(t, validTabcapFields(), fields)
	})

	t.Run("trims values and keeps optional fields", func(t *testing.T) {
		t.Parallel()
		in := validTabcapFields()
		in["resourcePack"] = "  Faithful 32x  "
		in["contact"] = " someone#1234 "
		in["note"] = "hi"
		fields, err := spec.ValidateFields(in)
		require.NoError(t, err)
		require.Equal(t, "Faithful 32x", fields["resourcePack"])
		require.Equal(t, "someone#1234", fields["contact"])
		require.Equal(t, "hi", fields["note"])
	})

	t.Run("drops empty optional fields", func(t *testing.T) {
		t.Parallel()
		in := validTabcapFields()
		in["contact"] = "  "
		in["note"] = ""
		fields, err := spec.ValidateFields(in)
		require.NoError(t, err)
		require.Equal(t, validTabcapFields(), fields)
	})

	t.Run("resource pack and gui scale are optional", func(t *testing.T) {
		t.Parallel()
		in := validTabcapFields()
		delete(in, "resourcePack")
		in["guiScale"] = " "
		fields, err := spec.ValidateFields(in)
		require.NoError(t, err)
		require.Equal(t, map[string]string{"launcher": "lunar", "mcVersion": "1.8.9"}, fields)
	})

	t.Run("other values", func(t *testing.T) {
		t.Parallel()
		in := validTabcapFields()
		in["launcher"] = "other"
		in["launcherOther"] = "TLauncher"
		in["mcVersion"] = "other"
		in["mcVersionOther"] = "1.17.1"
		fields, err := spec.ValidateFields(in)
		require.NoError(t, err)
		require.Equal(t, "TLauncher", fields["launcherOther"])
		require.Equal(t, "1.17.1", fields["mcVersionOther"])
	})

	invalid := map[string]func(map[string]string){
		"missing launcher":              func(f map[string]string) { delete(f, "launcher") },
		"unknown launcher":              func(f map[string]string) { f["launcher"] = "tlauncher" },
		"other launcher without text":   func(f map[string]string) { f["launcher"] = "other" },
		"launcher text without other":   func(f map[string]string) { f["launcherOther"] = "x" },
		"launcher text too long":        func(f map[string]string) { f["launcher"] = "other"; f["launcherOther"] = strings.Repeat("a", 101) },
		"missing mc version":            func(f map[string]string) { delete(f, "mcVersion") },
		"unknown mc version":            func(f map[string]string) { f["mcVersion"] = "1.7.10" },
		"other version without text":    func(f map[string]string) { f["mcVersion"] = "other" },
		"version text without other":    func(f map[string]string) { f["mcVersionOther"] = "1.17" },
		"other version not a version":   func(f map[string]string) { f["mcVersion"] = "other"; f["mcVersionOther"] = "latest" },
		"resource pack too long":        func(f map[string]string) { f["resourcePack"] = strings.Repeat("a", 201) },
		"bad gui scale":                 func(f map[string]string) { f["guiScale"] = "7" },
		"contact too long":              func(f map[string]string) { f["contact"] = strings.Repeat("a", 101) },
		"note too long":                 func(f map[string]string) { f["note"] = strings.Repeat("a", 1001) },
		"unknown field":                 func(f map[string]string) { f["client"] = "lunar" },
		"invalid utf8":                  func(f map[string]string) { f["resourcePack"] = "\xff" },
		"length counted in characters ": func(f map[string]string) { f["resourcePack"] = strings.Repeat("é", 201) },
	}
	for name, mutate := range invalid {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			in := validTabcapFields()
			mutate(in)
			_, err := spec.ValidateFields(in)
			require.ErrorIs(t, err, domain.ErrInvalidUpload)
		})
	}

	t.Run("200 multi-byte characters is fine", func(t *testing.T) {
		t.Parallel()
		in := validTabcapFields()
		in["resourcePack"] = strings.Repeat("é", 200)
		_, err := spec.ValidateFields(in)
		require.NoError(t, err)
	})
}

var makePNG = domaintest.NewPNG

func TestParsePNGHeader(t *testing.T) {
	t.Parallel()

	t.Run("rgba", func(t *testing.T) {
		t.Parallel()
		info, err := domain.ParsePNGHeader(makePNG(2560, 1440, 8, 6, 1000))
		require.NoError(t, err)
		require.Equal(t, domain.PNGInfo{Width: 2560, Height: 1440, BitDepth: 8, ColorType: "rgba"}, info)
	})

	t.Run("rgb, header only", func(t *testing.T) {
		t.Parallel()
		info, err := domain.ParsePNGHeader(makePNG(10, 20, 16, 2, 0)[:domain.PNGHeaderLen])
		require.NoError(t, err)
		require.Equal(t, domain.PNGInfo{Width: 10, Height: 20, BitDepth: 16, ColorType: "rgb"}, info)
	})

	invalid := map[string][]byte{
		"empty":         {},
		"not png":       []byte("GIF89a this is not a png at all, not even close"),
		"jpeg":          append([]byte{0xff, 0xd8, 0xff, 0xe0}, bytes.Repeat([]byte{0}, 40)...),
		"truncated":     makePNG(10, 10, 8, 2, 0)[:20],
		"zero width":    makePNG(0, 10, 8, 2, 0),
		"too wide":      makePNG(8193, 10, 8, 2, 0),
		"too tall":      makePNG(10, 8193, 8, 2, 0),
		"bad crc":       func() []byte { b := makePNG(10, 10, 8, 2, 0); b[29] ^= 0xff; return b }(),
		"palette":       makePNG(10, 10, 8, 3, 0),
		"bad bit depth": makePNG(10, 10, 3, 2, 0),
	}
	for name, data := range invalid {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			_, err := domain.ParsePNGHeader(data)
			require.ErrorIs(t, err, domain.ErrInvalidUpload)
		})
	}
}
