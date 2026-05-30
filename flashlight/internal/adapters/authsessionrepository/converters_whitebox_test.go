package authsessionrepository

import (
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/domain"
)

func TestIdentityTypeFromDB(t *testing.T) {
	t.Parallel()

	t.Run("anonymous round-trips", func(t *testing.T) {
		t.Parallel()
		got, err := identityTypeFromDB("anonymous")
		require.NoError(t, err)
		require.Equal(t, domain.AuthSessionIdentityAnonymous, got)
	})

	t.Run("unknown string returns error", func(t *testing.T) {
		t.Parallel()
		_, err := identityTypeFromDB("microsoft")
		require.Error(t, err)
	})

	t.Run("empty string returns error", func(t *testing.T) {
		t.Parallel()
		_, err := identityTypeFromDB("")
		require.Error(t, err)
	})
}

func TestIdentityTypeToDB(t *testing.T) {
	t.Parallel()

	t.Run("anonymous round-trips", func(t *testing.T) {
		t.Parallel()
		got, err := identityTypeToDB(domain.AuthSessionIdentityAnonymous)
		require.NoError(t, err)
		require.Equal(t, "anonymous", got)
	})

	t.Run("unknown domain value returns error", func(t *testing.T) {
		t.Parallel()
		_, err := identityTypeToDB(domain.AuthSessionIdentityType("bogus"))
		require.Error(t, err)
	})

	t.Run("empty domain value returns error", func(t *testing.T) {
		t.Parallel()
		_, err := identityTypeToDB("")
		require.Error(t, err)
	})
}
