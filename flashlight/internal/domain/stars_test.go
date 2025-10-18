package domain_test

import (
	"fmt"
	"testing"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/stretchr/testify/require"
)

func TestStarsToExperience(t *testing.T) {
	t.Parallel()

	tests := []struct {
		stars      int
		experience int64
	}{
		// Test cases yoinked from prism
		{1, 500},
		{3, 3500},
		{20, 87000},
		{481, 2340000},
		{1000, 4870000},
		{1091, 5312000},
	}

	for _, tt := range tests {
		t.Run(fmt.Sprintf("%d stars", tt.stars), func(t *testing.T) {
			t.Parallel()

			result := domain.StarsToExperience(tt.stars)
			require.Equal(t, tt.experience, result)
		})
	}
}

func TestExperienceToStars(t *testing.T) {
	t.Parallel()

	tests := []struct {
		experience int64
		stars      float64
	}{
		// Test cases from prism repository
		{
			experience: 500,
			stars:      1.0,
		},
		{
			experience: 3648,
			stars:      3 + 148.0/3500.0,
		},
		{
			experience: 89025,
			stars:      20 + 2025.0/5000.0,
		},
		{
			// Synthetic
			experience: 122986,
			stars:      27.0 + 986.0/5000.0,
		},
		{
			// Synthetic
			experience: 954638,
			stars:      196.0 + 638.0/5000.0,
		},
		{
			// Synthetic
			experience: 969078,
			stars:      199.0 + 78.0/5000.,
		},
		{
			// Synthetic
			experience: 975611,
			stars:      202.0 + 111.0/2000.,
		},
		{
			// Synthetic
			experience: 977587,
			stars:      203.0 + 87.0/3500.,
		},
		{
			experience: 2344717,
			stars:      481 + 4717.0/5000.0,
		},
		{
			experience: 4870331,
			stars:      1000 + 331.0/500.0,
		},
		{
			experience: 5316518,
			stars:      1091 + 4518.0/5000.0,
		},
	}

	for _, tt := range tests {
		t.Run(fmt.Sprintf("%d experience", tt.experience), func(t *testing.T) {
			t.Parallel()

			require.Equal(t, tt.stars, domain.ExperienceToStars(tt.experience))
		})
	}
}
