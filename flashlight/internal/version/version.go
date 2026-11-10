// Package version parses and compares prism release version strings of the
// form vMAJOR.MINOR.PATCH or vMAJOR.MINOR.PATCH-SUFFIX (treated as a dev
// version). It mirrors prism's prism.version.VersionInfo.
package version

import (
	"fmt"
	"strconv"
	"strings"
)

// Version is a parsed prism version. Dev is true if the input had any "-suffix"
// after the patch component (e.g. "v1.3.1-dev").
type Version struct {
	Major int
	Minor int
	Patch int
	Dev   bool
}

// Parse parses a version string like "v1.2.3" or "v1.2.3-dev".
func Parse(s string) (Version, error) {
	if s == "" {
		return Version{}, fmt.Errorf("empty version string")
	}

	if s[0] == 'v' {
		s = s[1:]
	}

	parts := strings.SplitN(s, ".", 4)
	if len(parts) != 3 {
		return Version{}, fmt.Errorf("expected 3 components in %q, got %d", s, len(parts))
	}

	patchStr := parts[2]
	dev := false
	if i := strings.Index(patchStr, "-"); i >= 0 {
		patchStr = patchStr[:i]
		dev = true
	}

	major, err := strconv.Atoi(parts[0])
	if err != nil {
		return Version{}, fmt.Errorf("invalid major %q: %w", parts[0], err)
	}
	minor, err := strconv.Atoi(parts[1])
	if err != nil {
		return Version{}, fmt.Errorf("invalid minor %q: %w", parts[1], err)
	}
	patch, err := strconv.Atoi(patchStr)
	if err != nil {
		return Version{}, fmt.Errorf("invalid patch %q: %w", patchStr, err)
	}

	return Version{Major: major, Minor: minor, Patch: patch, Dev: dev}, nil
}

// MustParse panics on parse error. Intended for package-level constants.
func MustParse(s string) Version {
	v, err := Parse(s)
	if err != nil {
		panic(fmt.Sprintf("version.MustParse(%q): %v", s, err))
	}
	return v
}

// IsAtLeast reports whether v is numerically greater than or equal to other.
// The dev flag is ignored.
func (v Version) IsAtLeast(other Version) bool {
	return cmp3(
		[3]int{v.Major, v.Minor, v.Patch},
		[3]int{other.Major, other.Minor, other.Patch},
	) >= 0
}

// UpdateAvailable reports whether `latest` is newer than `v`.
//
// If ignorePatchBumps is true, only the (major, minor) pair is compared, so a
// patch-only bump (e.g. v1.2.3 -> v1.2.4) is not considered an update.
//
// When the numeric components match exactly, a dev version is considered
// older than the corresponding non-dev release (so "v1.2.3-dev" -> "v1.2.3"
// is reported as an update).
func (v Version) UpdateAvailable(latest Version, ignorePatchBumps bool) bool {
	currentMM := [2]int{v.Major, v.Minor}
	latestMM := [2]int{latest.Major, latest.Minor}

	if ignorePatchBumps {
		return cmp2(latestMM, currentMM) > 0
	}

	currentMMP := [3]int{v.Major, v.Minor, v.Patch}
	latestMMP := [3]int{latest.Major, latest.Minor, latest.Patch}

	if cmp3(latestMMP, currentMMP) > 0 {
		return true
	}

	if currentMMP == latestMMP && v.Dev && !latest.Dev {
		return true
	}

	return false
}

func cmp2(a, b [2]int) int {
	for i := range a {
		if a[i] != b[i] {
			if a[i] < b[i] {
				return -1
			}
			return 1
		}
	}
	return 0
}

func cmp3(a, b [3]int) int {
	for i := range a {
		if a[i] != b[i] {
			if a[i] < b[i] {
				return -1
			}
			return 1
		}
	}
	return 0
}
