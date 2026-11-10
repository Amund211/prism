package domain

import (
	"fmt"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestExpPerPrestige(t *testing.T) {
	t.Parallel()
	expFor100Levels := 0
	for star := range 100 {
		expFor100Levels += expUntilNextStar(star)
	}

	require.Equal(t, expFor100Levels, expPerPrestige)
}

func TestExpUntilNextStar(t *testing.T) {
	t.Parallel()
	tests := []struct {
		star     int
		expected int
	}{
		{0, 500}, // NOTE: A new hypixel account starts at 1 star (500 exp)
		{1, 1000},
		{2, 2000},
		{3, 3500},
		{4, 5000},
		{5, 5000},
		{6, 5000},
		{7, 5000},
		// ...
		{97, 5000},
		{98, 5000},
		{99, 5000},
		{100, 500},
		{101, 1000},
		{102, 2000},
		{103, 3500},
		{104, 5000},
		{105, 5000},
		// ...
		{197, 5000},
		{198, 5000},
		{199, 5000},
		{200, 500},
		{201, 1000},
		{202, 2000},
		{203, 3500},
		{204, 5000},
		{205, 5000},
		// ...
		{297, 5000},
		{298, 5000},
		{299, 5000},
		{300, 500},
		{301, 1000},
		{302, 2000},
		{303, 3500},
		{304, 5000},
		{305, 5000},
	}

	for _, test := range tests {
		t.Run(fmt.Sprintf("star=%d", test.star), func(t *testing.T) {
			t.Parallel()
			require.Equal(t, test.expected, expUntilNextStar(test.star))
		})
	}
}
