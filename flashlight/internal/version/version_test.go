package version_test

import (
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/version"
)

func TestParse(t *testing.T) {
	t.Parallel()

	cases := []struct {
		input    string
		expected version.Version
		wantErr  bool
	}{
		{input: "v1.0.0", expected: version.Version{Major: 1, Minor: 0, Patch: 0}},
		{input: "v1.0.1", expected: version.Version{Major: 1, Minor: 0, Patch: 1}},
		{input: "v1.1.1", expected: version.Version{Major: 1, Minor: 1, Patch: 1}},
		{input: "v2.1.1", expected: version.Version{Major: 2, Minor: 1, Patch: 1}},
		{input: "v1.3.1-dev", expected: version.Version{Major: 1, Minor: 3, Patch: 1, Dev: true}},
		{input: "v1.3.1-lol", expected: version.Version{Major: 1, Minor: 3, Patch: 1, Dev: true}},
		// Without leading v
		{input: "1.2.3", expected: version.Version{Major: 1, Minor: 2, Patch: 3}},
		// Invalid strings
		{input: "v1.2.3.4.5", wantErr: true},
		{input: "va.b.c", wantErr: true},
		{input: "v1.2", wantErr: true},
		{input: "", wantErr: true},
	}

	for _, c := range cases {
		t.Run(c.input, func(t *testing.T) {
			t.Parallel()
			got, err := version.Parse(c.input)
			if c.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
			require.Equal(t, c.expected, got)
		})
	}
}

func TestUpdateAvailable(t *testing.T) {
	t.Parallel()

	cases := []struct {
		current   string
		latest    string
		minorBump bool // expected when ignorePatchBumps=true
		patchBump bool // expected when ignorePatchBumps=false
	}{
		{"v2.1.0", "v2.1.0", false, false},
		{"v2.0.0", "v2.1.0", true, true},
		{"v1.0.1", "v2.1.0", true, true},
		{"v1.0.0", "v2.1.0", true, true},
		{"v2.1.0", "v2.1.1", false, true},
		{"v1.0.1-dev", "v1.0.1", false, true},
		{"v2.1.0", "v2.0.9", false, false},
	}

	for _, c := range cases {
		t.Run(c.current+"->"+c.latest, func(t *testing.T) {
			t.Parallel()
			current, err := version.Parse(c.current)
			require.NoError(t, err)
			latest, err := version.Parse(c.latest)
			require.NoError(t, err)

			require.Equal(t, c.minorBump, current.UpdateAvailable(latest, true))
			require.Equal(t, c.patchBump, current.UpdateAvailable(latest, false))
		})
	}
}

func TestIsAtLeast(t *testing.T) {
	t.Parallel()

	v := func(s string) version.Version { return version.MustParse(s) }

	cases := []struct {
		current  version.Version
		other    version.Version
		expected bool
	}{
		{v("v1.11.1"), v("v1.11.1"), true},
		{v("v1.11.1-dev"), v("v1.11.1"), true},
		{v("v1.11.0"), v("v1.11.1"), false},
		{v("v2.0.0"), v("v1.11.1"), true},
		{v("v1.10.5"), v("v1.11.0"), false},
	}

	for _, c := range cases {
		t.Run("", func(t *testing.T) {
			t.Parallel()
			require.Equal(t, c.expected, c.current.IsAtLeast(c.other))
		})
	}
}

func TestMustParse(t *testing.T) {
	t.Parallel()

	t.Run("valid", func(t *testing.T) {
		t.Parallel()
		v := version.MustParse("v1.2.3")
		require.Equal(t, version.Version{Major: 1, Minor: 2, Patch: 3}, v)
	})

	t.Run("invalid panics", func(t *testing.T) {
		t.Parallel()
		require.Panics(t, func() {
			version.MustParse("nope")
		})
	})
}
