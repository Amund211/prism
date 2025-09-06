package domain_test

import (
	"fmt"
	"testing"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/stretchr/testify/require"
)

func TestStarsToExperience(t *testing.T) {
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
			result := domain.StarsToExperience(tt.stars)
			require.Equal(t, tt.experience, result)
		})
	}
}

func TestExperienceToStars(t *testing.T) {
	tests := []struct {
		experience int64
		stars      int
	}{
		// Test cases yoinked from prism
		{500, 1},
		{3500, 3},
		{87000, 20},
		{2340000, 481},
		{4870000, 1000},
		{5312000, 1091},
	}

	for _, tt := range tests {
		t.Run(fmt.Sprintf("%d experience", tt.experience), func(t *testing.T) {
			result := domain.ExperienceToStars(tt.experience)
			require.Equal(t, tt.stars, result)
		})
	}
}
