package app_test

import (
	"context"
	"testing"
	"time"

	"github.com/Amund211/flashlight/internal/adapters/cache"
	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type mockUUIDProvider struct {
	t *testing.T

	getAccountByUsernameUsername string
	getAccountByUsernameCalled   bool
	getAccountByUsernameAccount  domain.Account
	getAccountByUsernameErr      error
}

func (m *mockUUIDProvider) GetAccountByUsername(ctx context.Context, username string) (domain.Account, error) {
	m.t.Helper()
	require.Equal(m.t, m.getAccountByUsernameUsername, username)

	require.False(m.t, m.getAccountByUsernameCalled)

	m.getAccountByUsernameCalled = true
	return m.getAccountByUsernameAccount, m.getAccountByUsernameErr
}

type mockAccountRepository struct {
	t *testing.T

	getAccountByUsernameUsername string
	getAccountByUsernameCalled   bool
	getAccountByUsernameAccount  domain.Account
	getAccountByUsernameErr      error

	removeUsernameUsername string
	removeUsernameCalled   bool
	removeUsernameErr      error

	storeAccountAccount domain.Account
	storeAccountCalled  bool
	storeAccountErr     error
}

func (m *mockAccountRepository) GetAccountByUsername(ctx context.Context, username string) (domain.Account, error) {
	m.t.Helper()
	require.Equal(m.t, m.getAccountByUsernameUsername, username)

	require.False(m.t, m.getAccountByUsernameCalled)

	m.getAccountByUsernameCalled = true
	return m.getAccountByUsernameAccount, m.getAccountByUsernameErr
}

func (m *mockAccountRepository) RemoveUsername(ctx context.Context, username string) error {
	m.t.Helper()
	require.Equal(m.t, m.removeUsernameUsername, username)

	require.False(m.t, m.removeUsernameCalled)

	m.removeUsernameCalled = true
	return m.removeUsernameErr
}

func (m *mockAccountRepository) StoreAccount(ctx context.Context, account domain.Account) error {
	m.t.Helper()
	require.Equal(m.t, m.storeAccountAccount, account)

	require.False(m.t, m.storeAccountCalled)

	m.storeAccountCalled = true
	return m.storeAccountErr
}

func TestBuildGetUUIDWithCache(t *testing.T) {
	t.Parallel()

	ctx := context.Background()
	now := time.Now()
	nowFunc := func() time.Time {
		return now
	}
	UUID := "12345678-1234-1234-1234-123456789012"

	t.Run("miss in repo results in call to provider and store to repo", func(t *testing.T) {
		t.Parallel()

		c := cache.NewBasicCache[string]()
		provider := &mockUUIDProvider{
			t:                            t,
			getAccountByUsernameUsername: "testuser",
			getAccountByUsernameAccount: domain.Account{
				Username:  "TestUser",
				UUID:      UUID,
				QueriedAt: now,
			},
		}
		repo := &mockAccountRepository{
			t:                            t,
			getAccountByUsernameUsername: "testuser",
			getAccountByUsernameErr:      domain.ErrUsernameNotFound,

			storeAccountAccount: domain.Account{
				UUID:      UUID,
				Username:  "TestUser",
				QueriedAt: now,
			},
		}
		getUUIDWithCache := app.BuildGetUUIDWithCache(c, provider, repo, nowFunc)

		uuid, err := getUUIDWithCache(ctx, "testuser")
		require.NoError(t, err)
		require.Equal(t, UUID, uuid)

		require.True(t, repo.getAccountByUsernameCalled)
		require.True(t, provider.getAccountByUsernameCalled)
		require.True(t, repo.storeAccountCalled)
		require.False(t, repo.removeUsernameCalled)
	})

	t.Run("recent hit in repo results in no call to provider", func(t *testing.T) {
		t.Parallel()
		for _, repoAge := range []time.Duration{
			0,
			time.Minute,
			time.Hour,
			24 * time.Hour,
			10 * 23.9 * time.Hour, // almost 10 days
		} {
			t.Run("repo age "+repoAge.String(), func(t *testing.T) {
				t.Parallel()

				c := cache.NewBasicCache[string]()
				provider := &mockUUIDProvider{
					t: t,
				}
				repo := &mockAccountRepository{
					t:                            t,
					getAccountByUsernameUsername: "testuser",
					getAccountByUsernameAccount: domain.Account{
						UUID:      UUID,
						Username:  "TestUser",
						QueriedAt: now.Add(-repoAge),
					},

					storeAccountAccount: domain.Account{
						UUID:      UUID,
						Username:  "testuser",
						QueriedAt: now,
					},
				}
				getUUIDWithCache := app.BuildGetUUIDWithCache(c, provider, repo, nowFunc)

				uuid, err := getUUIDWithCache(ctx, "testuser")
				require.NoError(t, err)
				require.Equal(t, UUID, uuid)

				require.True(t, repo.getAccountByUsernameCalled)
				require.False(t, provider.getAccountByUsernameCalled)
				require.False(t, repo.storeAccountCalled)
				require.False(t, repo.removeUsernameCalled)
			})
		}
	})

	t.Run("non-recent hit in repo results in call to provider and store to repo", func(t *testing.T) {
		t.Parallel()
		for _, repoAge := range []time.Duration{
			10 * 24.1 * time.Hour, // a bit more than 10 days
			20 * 24 * time.Hour,
			30 * 24 * time.Hour,
			60 * 24 * time.Hour,
		} {
			t.Run("repo age "+repoAge.String(), func(t *testing.T) {
				t.Parallel()

				c := cache.NewBasicCache[string]()
				provider := &mockUUIDProvider{
					t:                            t,
					getAccountByUsernameUsername: "testuser",
					getAccountByUsernameAccount: domain.Account{
						Username:  "TestUser",
						UUID:      UUID,
						QueriedAt: now,
					},
				}
				repo := &mockAccountRepository{
					t:                            t,
					getAccountByUsernameUsername: "testuser",
					getAccountByUsernameAccount: domain.Account{
						UUID:      UUID,
						Username:  "testuser",
						QueriedAt: now.Add(-repoAge),
					},

					storeAccountAccount: domain.Account{
						UUID:      UUID,
						Username:  "TestUser",
						QueriedAt: now,
					},
				}
				getUUIDWithCache := app.BuildGetUUIDWithCache(c, provider, repo, nowFunc)

				uuid, err := getUUIDWithCache(ctx, "testuser")
				require.NoError(t, err)
				require.Equal(t, UUID, uuid)

				require.True(t, repo.getAccountByUsernameCalled)
				require.True(t, provider.getAccountByUsernameCalled)
				require.True(t, repo.storeAccountCalled)
				require.False(t, repo.removeUsernameCalled)
			})
		}
	})

	t.Run("error in repo get results in call to provider and store to repo", func(t *testing.T) {
		t.Parallel()
		for _, repoErr := range []error{
			domain.ErrUsernameNotFound,
			domain.ErrTemporarilyUnavailable,
			assert.AnError,
		} {
			t.Run("repo get error: "+repoErr.Error(), func(t *testing.T) {
				t.Parallel()

				c := cache.NewBasicCache[string]()
				provider := &mockUUIDProvider{
					t:                            t,
					getAccountByUsernameUsername: "testuser",
					getAccountByUsernameAccount: domain.Account{
						Username:  "TestUser",
						UUID:      UUID,
						QueriedAt: now,
					},
				}
				repo := &mockAccountRepository{
					t:                            t,
					getAccountByUsernameUsername: "testuser",
					getAccountByUsernameErr:      repoErr,

					storeAccountAccount: domain.Account{
						UUID:      UUID,
						Username:  "TestUser",
						QueriedAt: now,
					},
				}
				getUUIDWithCache := app.BuildGetUUIDWithCache(c, provider, repo, nowFunc)

				uuid, err := getUUIDWithCache(ctx, "testuser")
				require.NoError(t, err)
				require.Equal(t, UUID, uuid)

				require.True(t, repo.getAccountByUsernameCalled)
				require.True(t, provider.getAccountByUsernameCalled)
				require.True(t, repo.storeAccountCalled)
				require.False(t, repo.removeUsernameCalled)
			})
		}
	})

	t.Run("not found in provider get results in call to remove in repo", func(t *testing.T) {
		t.Parallel()

		c := cache.NewBasicCache[string]()
		provider := &mockUUIDProvider{
			t:                            t,
			getAccountByUsernameUsername: "testuser",
			getAccountByUsernameErr:      domain.ErrUsernameNotFound,
		}
		repo := &mockAccountRepository{
			t:                            t,
			getAccountByUsernameUsername: "testuser",
			getAccountByUsernameAccount: domain.Account{
				UUID:      UUID,
				Username:  "testuser",
				QueriedAt: now.Add(-12 * 24 * time.Hour),
			},

			removeUsernameUsername: "testuser",
		}
		getUUIDWithCache := app.BuildGetUUIDWithCache(c, provider, repo, nowFunc)

		uuid, err := getUUIDWithCache(ctx, "testuser")
		require.ErrorIs(t, err, domain.ErrUsernameNotFound)
		require.Empty(t, uuid)

		require.True(t, repo.getAccountByUsernameCalled)
		require.True(t, provider.getAccountByUsernameCalled)
		require.False(t, repo.storeAccountCalled)
		require.True(t, repo.removeUsernameCalled)
	})

	t.Run("error in provider get results in fallback to recent-ish repo hit", func(t *testing.T) {
		t.Parallel()
		for _, repoAge := range []time.Duration{
			10 * 24.1 * time.Hour, // a bit more than 10 days
			20 * 24 * time.Hour,
			36 * 24 * time.Hour,
		} {
			t.Run("repo age "+repoAge.String(), func(t *testing.T) {
				t.Parallel()

				c := cache.NewBasicCache[string]()
				provider := &mockUUIDProvider{
					t:                            t,
					getAccountByUsernameUsername: "testuser",
					getAccountByUsernameErr:      assert.AnError,
				}
				repo := &mockAccountRepository{
					t:                            t,
					getAccountByUsernameUsername: "testuser",
					getAccountByUsernameAccount: domain.Account{
						UUID:      UUID,
						Username:  "testuser",
						QueriedAt: now.Add(-repoAge),
					},

					removeUsernameUsername: "testuser",
				}
				getUUIDWithCache := app.BuildGetUUIDWithCache(c, provider, repo, nowFunc)

				uuid, err := getUUIDWithCache(ctx, "testuser")
				require.NoError(t, err)
				require.Equal(t, UUID, uuid)

				require.True(t, repo.getAccountByUsernameCalled)
				require.True(t, provider.getAccountByUsernameCalled)
				require.False(t, repo.storeAccountCalled)
				require.False(t, repo.removeUsernameCalled)
			})
		}
	})

	t.Run("error in provider get results in error if no recent-ish repo hit to fall back to", func(t *testing.T) {
		t.Parallel()
		for _, repoAge := range []time.Duration{
			38 * 24 * time.Hour,
			50 * 24 * time.Hour,
			100 * 24 * time.Hour,
		} {
			t.Run("repo age "+repoAge.String(), func(t *testing.T) {
				t.Parallel()

				c := cache.NewBasicCache[string]()
				provider := &mockUUIDProvider{
					t:                            t,
					getAccountByUsernameUsername: "testuser",
					getAccountByUsernameErr:      assert.AnError,
				}
				repo := &mockAccountRepository{
					t:                            t,
					getAccountByUsernameUsername: "testuser",
					getAccountByUsernameAccount: domain.Account{
						UUID:      UUID,
						Username:  "testUSER",
						QueriedAt: now.Add(-repoAge),
					},

					removeUsernameUsername: "testuser",
				}
				getUUIDWithCache := app.BuildGetUUIDWithCache(c, provider, repo, nowFunc)

				uuid, err := getUUIDWithCache(ctx, "testuser")
				require.ErrorIs(t, err, assert.AnError)
				require.Empty(t, uuid)

				require.True(t, repo.getAccountByUsernameCalled)
				require.True(t, provider.getAccountByUsernameCalled)
				require.False(t, repo.storeAccountCalled)
				require.False(t, repo.removeUsernameCalled)
			})
		}
	})

	t.Run("cache hit results in no calls", func(t *testing.T) {
		t.Parallel()

		c := cache.NewBasicCache[string]()
		provider := &mockUUIDProvider{
			t:                            t,
			getAccountByUsernameUsername: "testuser",
			getAccountByUsernameAccount: domain.Account{
				Username:  "testuser",
				UUID:      UUID,
				QueriedAt: now,
			},
		}
		repo := &mockAccountRepository{
			t:                            t,
			getAccountByUsernameUsername: "testuser",
			getAccountByUsernameErr:      domain.ErrUsernameNotFound,

			storeAccountAccount: domain.Account{
				UUID:      UUID,
				Username:  "testuser",
				QueriedAt: now,
			},
		}
		getUUIDWithCache := app.BuildGetUUIDWithCache(c, provider, repo, nowFunc)

		uuid, err := getUUIDWithCache(ctx, "testuser")
		require.NoError(t, err)
		require.Equal(t, UUID, uuid)

		provider = &mockUUIDProvider{
			t: t,
		}
		repo = &mockAccountRepository{
			t: t,
		}
		getUUIDWithCache = app.BuildGetUUIDWithCache(c, provider, repo, nowFunc)

		uuid, err = getUUIDWithCache(ctx, "testuser")
		require.NoError(t, err)
		require.Equal(t, UUID, uuid)

		// We should have hit the cache, so no calls to provider or repo
		require.False(t, provider.getAccountByUsernameCalled)
		require.False(t, repo.getAccountByUsernameCalled)
		require.False(t, repo.storeAccountCalled)
		require.False(t, repo.removeUsernameCalled)
	})
}
