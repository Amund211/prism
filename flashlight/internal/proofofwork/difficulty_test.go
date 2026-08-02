package proofofwork_test

import (
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/proofofwork"
)

func TestBuildDifficultyFunc(t *testing.T) {
	t.Parallel()

	t.Run("every caller gets the global floor", func(t *testing.T) {
		t.Parallel()
		difficultyFor, err := proofofwork.BuildDifficultyFunc(7)
		require.NoError(t, err)

		for _, in := range []proofofwork.DifficultyInput{
			{},
			{IPHash: testIPHash, ClientType: "prism"},
			{IPHash: "other", ClientType: "rainbow"},
		} {
			require.Equal(t, 7, difficultyFor(in))
		}
	})

	t.Run("the shipped default is zero", func(t *testing.T) {
		t.Parallel()
		difficultyFor, err := proofofwork.BuildDifficultyFunc(proofofwork.DefaultDifficulty)
		require.NoError(t, err)
		require.Equal(t, 0, difficultyFor(proofofwork.DifficultyInput{IPHash: testIPHash, ClientType: "prism"}))
	})

	t.Run("rejects a floor outside the sanity ceiling", func(t *testing.T) {
		t.Parallel()
		for _, floor := range []int{-1, proofofwork.MaxDifficulty + 1, 1000} {
			_, err := proofofwork.BuildDifficultyFunc(floor)
			require.ErrorIs(t, err, proofofwork.ErrInvalidConfig)
		}
	})
}
