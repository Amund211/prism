package domain_test

import (
	"strings"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/domain"
)

func TestIsValidUsername(t *testing.T) {
	t.Parallel()

	valid := []string{
		"a",
		"ab",
		"Notch",
		"some_guy",
		strings.Repeat("a", 16),
		strings.Repeat("a", 25),
		// Legacy names, or names Mojang does not reject
		"Cool.J.1",
		"Daniel B.1",
		"a-b-c",
		"x$y",
		"user@mail.com",
		"a+b",
		"a!b",
		"a?b",
		"a%b",
		"a~b",
	}
	for _, username := range valid {
		t.Run("valid "+username, func(t *testing.T) {
			t.Parallel()
			require.True(t, domain.IsValidUsername(username))
		})
	}

	invalid := []string{
		"",
		strings.Repeat("a", 26),
		"ランクやエメラルドはショップで購入できます",
		"æøå",
		"§ko01Y",
		"foo�bar",
		"Steve#8",
		"a&b",
		"a/b",
		`a\b`,
		"a\tb",
		"a\nb",
		"a\x00b",
		"a\x7fb",
	}
	for _, username := range invalid {
		t.Run("invalid "+username, func(t *testing.T) {
			t.Parallel()
			require.False(t, domain.IsValidUsername(username))
		})
	}
}
