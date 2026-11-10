package app

import (
	"context"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/adapters/cache"
	"github.com/Amund211/flashlight/internal/domain"
)

type countingUserRepository struct {
	user  domain.User
	err   error
	calls int
}

func (c *countingUserRepository) GetUser(ctx context.Context, userID string) (domain.User, error) {
	c.calls++
	if c.err != nil {
		return domain.User{}, c.err
	}
	return c.user, nil
}

func TestGetUserWithCache(t *testing.T) {
	t.Parallel()

	build := func(t *testing.T, repo getUserRepository) GetUser {
		t.Helper()
		getUser, err := BuildGetUserWithCache(cache.NewBasicCache[domain.User](), repo)
		require.NoError(t, err)
		return getUser
	}

	t.Run("returns the user from the repository", func(t *testing.T) {
		t.Parallel()

		repo := &countingUserRepository{
			user: domain.User{UserID: "user-1", FirstSeenAt: time.Date(2025, time.January, 1, 0, 0, 0, 0, time.UTC), SeenCount: 3},
		}
		getUser := build(t, repo)

		user, err := getUser(t.Context(), "user-1")
		require.NoError(t, err)
		require.Equal(t, repo.user, user)
	})

	t.Run("found users are cached", func(t *testing.T) {
		t.Parallel()

		repo := &countingUserRepository{
			user: domain.User{UserID: "user-1"},
		}
		getUser := build(t, repo)

		user, err := getUser(t.Context(), "user-1")
		require.NoError(t, err)
		require.Equal(t, repo.user, user)

		user, err = getUser(t.Context(), "user-1")
		require.NoError(t, err)
		require.Equal(t, repo.user, user)

		require.Equal(t, 1, repo.calls)
	})

	t.Run("not found is passed through and not cached", func(t *testing.T) {
		t.Parallel()

		repo := &countingUserRepository{err: domain.ErrUserNotFound}
		getUser := build(t, repo)

		_, err := getUser(t.Context(), "user-1")
		require.ErrorIs(t, err, domain.ErrUserNotFound)

		_, err = getUser(t.Context(), "user-1")
		require.ErrorIs(t, err, domain.ErrUserNotFound)

		require.Equal(t, 2, repo.calls)
	})

	t.Run("repository errors are passed through and not cached", func(t *testing.T) {
		t.Parallel()

		repo := &countingUserRepository{err: assert.AnError}
		getUser := build(t, repo)

		_, err := getUser(t.Context(), "user-1")
		require.ErrorIs(t, err, assert.AnError)

		_, err = getUser(t.Context(), "user-1")
		require.ErrorIs(t, err, assert.AnError)

		require.Equal(t, 2, repo.calls)
	})
}
