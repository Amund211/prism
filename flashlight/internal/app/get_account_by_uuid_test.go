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

type mockAccountProviderByUUID struct {
	t *testing.T

	getAccountByUUIDUUID    string
	getAccountByUUIDCalled  bool
	getAccountByUUIDAccount domain.Account
	getAccountByUUIDErr     error
}

func (m *mockAccountProviderByUUID) GetAccountByUUID(ctx context.Context, uuid string) (domain.Account, error) {
	m.t.Helper()
	require.Equal(m.t, m.getAccountByUUIDUUID, uuid)

	require.False(m.t, m.getAccountByUUIDCalled)

	m.getAccountByUUIDCalled = true
	return m.getAccountByUUIDAccount, m.getAccountByUUIDErr
}

type mockAccountRepositoryByUUID struct {
	t *testing.T

	getAccountByUUIDUUID    string
	getAccountByUUIDCalled  bool
	getAccountByUUIDAccount domain.Account
	getAccountByUUIDErr     error

	storeAccountAccount domain.Account
	storeAccountCalled  bool
	storeAccountErr     error
}

func (m *mockAccountRepositoryByUUID) GetAccountByUUID(ctx context.Context, uuid string) (domain.Account, error) {
	m.t.Helper()
	require.Equal(m.t, m.getAccountByUUIDUUID, uuid)

	require.False(m.t, m.getAccountByUUIDCalled)

	m.getAccountByUUIDCalled = true
	return m.getAccountByUUIDAccount, m.getAccountByUUIDErr
}

func (m *mockAccountRepositoryByUUID) StoreAccount(ctx context.Context, account domain.Account) error {
	m.t.Helper()
	require.Equal(m.t, m.storeAccountAccount, account)

	require.False(m.t, m.storeAccountCalled)

	m.storeAccountCalled = true
	return m.storeAccountErr
}

func TestBuildGetAccountByUUIDWithCache(t *testing.T) {
	t.Parallel()

	ctx := t.Context()
	now := time.Now()
	nowFunc := func() time.Time {
		return now
	}
	UUID := "12345678-1234-1234-1234-123456789012"

	t.Run("call to provider and store to repo", func(t *testing.T) {
		t.Parallel()

		c := cache.NewBasicCache[domain.Account]()
		provider := &mockAccountProviderByUUID{
			t:                    t,
			getAccountByUUIDUUID: UUID,
			getAccountByUUIDAccount: domain.Account{
				Username:  "TestUser",
				UUID:      UUID,
				QueriedAt: now,
			},
		}
		repo := &mockAccountRepositoryByUUID{
			t: t,
			storeAccountAccount: domain.Account{
				UUID:      UUID,
				Username:  "TestUser",
				QueriedAt: now,
			},
		}
		getAccountByUUIDWithCache, err := app.BuildGetAccountByUUIDWithCache(c, provider, repo, nowFunc)
		require.NoError(t, err)

		account, err := getAccountByUUIDWithCache(ctx, UUID)
		require.NoError(t, err)
		require.Equal(t, domain.Account{
			Username:  "TestUser",
			UUID:      UUID,
			QueriedAt: now,
		}, account)

		require.True(t, provider.getAccountByUUIDCalled)
		require.False(t, repo.getAccountByUUIDCalled)
		require.True(t, repo.storeAccountCalled)
	})

	t.Run("not found in provider results in no more calls", func(t *testing.T) {
		t.Parallel()

		c := cache.NewBasicCache[domain.Account]()
		provider := &mockAccountProviderByUUID{
			t:                    t,
			getAccountByUUIDUUID: UUID,
			getAccountByUUIDErr:  domain.ErrUsernameNotFound,
		}
		repo := &mockAccountRepositoryByUUID{
			t: t,
		}
		getAccountByUUIDWithCache, err := app.BuildGetAccountByUUIDWithCache(c, provider, repo, nowFunc)
		require.NoError(t, err)

		_, err = getAccountByUUIDWithCache(ctx, UUID)
		require.ErrorIs(t, err, domain.ErrUsernameNotFound)

		require.True(t, provider.getAccountByUUIDCalled)
		require.False(t, repo.getAccountByUUIDCalled)
		require.False(t, repo.storeAccountCalled)
	})

	t.Run("error in provider get results in fallback to recent-ish repo hit", func(t *testing.T) {
		t.Parallel()
		for _, repoAge := range []time.Duration{
			1 * time.Minute,
			1 * time.Hour,
			24 * time.Hour,
			10 * 24 * time.Hour,
			20 * 24 * time.Hour,
			29 * 24 * time.Hour,
		} {
			t.Run("repo age "+repoAge.String(), func(t *testing.T) {
				t.Parallel()

				c := cache.NewBasicCache[domain.Account]()
				provider := &mockAccountProviderByUUID{
					t:                    t,
					getAccountByUUIDUUID: UUID,
					getAccountByUUIDErr:  assert.AnError,
				}
				repo := &mockAccountRepositoryByUUID{
					t:                    t,
					getAccountByUUIDUUID: UUID,
					getAccountByUUIDAccount: domain.Account{
						UUID:      UUID,
						Username:  "testuser",
						QueriedAt: now.Add(-repoAge),
					},
				}
				getAccountByUUIDWithCache, err := app.BuildGetAccountByUUIDWithCache(c, provider, repo, nowFunc)
				require.NoError(t, err)

				account, err := getAccountByUUIDWithCache(ctx, UUID)
				require.NoError(t, err)
				require.Equal(t, domain.Account{
					UUID:      UUID,
					Username:  "testuser",
					QueriedAt: now.Add(-repoAge),
				}, account)

				require.True(t, repo.getAccountByUUIDCalled)
				require.True(t, provider.getAccountByUUIDCalled)
				require.False(t, repo.storeAccountCalled)
			})
		}
	})

	t.Run("error in provider get results in error if no recent-ish repo hit to fall back to", func(t *testing.T) {
		t.Parallel()
		for _, repoAge := range []time.Duration{
			31 * 24 * time.Hour,
			50 * 24 * time.Hour,
			100 * 24 * time.Hour,
		} {
			t.Run("repo age "+repoAge.String(), func(t *testing.T) {
				t.Parallel()

				c := cache.NewBasicCache[domain.Account]()
				provider := &mockAccountProviderByUUID{
					t:                    t,
					getAccountByUUIDUUID: UUID,
					getAccountByUUIDErr:  assert.AnError,
				}
				repo := &mockAccountRepositoryByUUID{
					t:                    t,
					getAccountByUUIDUUID: UUID,
					getAccountByUUIDAccount: domain.Account{
						UUID:      UUID,
						Username:  "testUSER",
						QueriedAt: now.Add(-repoAge),
					},
				}
				getAccountByUUIDWithCache, err := app.BuildGetAccountByUUIDWithCache(c, provider, repo, nowFunc)
				require.NoError(t, err)

				_, err = getAccountByUUIDWithCache(ctx, UUID)
				require.ErrorIs(t, err, assert.AnError)

				require.True(t, repo.getAccountByUUIDCalled)
				require.True(t, provider.getAccountByUUIDCalled)
				require.False(t, repo.storeAccountCalled)
			})
		}
	})

	t.Run("cache hit results in no calls", func(t *testing.T) {
		t.Parallel()

		c := cache.NewBasicCache[domain.Account]()
		provider := &mockAccountProviderByUUID{
			t:                    t,
			getAccountByUUIDUUID: UUID,
			getAccountByUUIDAccount: domain.Account{
				Username:  "testuser",
				UUID:      UUID,
				QueriedAt: now,
			},
		}
		repo := &mockAccountRepositoryByUUID{
			t: t,

			storeAccountAccount: domain.Account{
				UUID:      UUID,
				Username:  "testuser",
				QueriedAt: now,
			},
		}
		getAccountByUUIDWithCache, err := app.BuildGetAccountByUUIDWithCache(c, provider, repo, nowFunc)
		require.NoError(t, err)

		account, err := getAccountByUUIDWithCache(ctx, UUID)
		require.NoError(t, err)
		require.Equal(t, domain.Account{
			Username:  "testuser",
			UUID:      UUID,
			QueriedAt: now,
		}, account)

		provider = &mockAccountProviderByUUID{
			t: t,
		}
		repo = &mockAccountRepositoryByUUID{
			t: t,
		}
		getAccountByUUIDWithCache, err = app.BuildGetAccountByUUIDWithCache(c, provider, repo, nowFunc)
		require.NoError(t, err)

		account, err = getAccountByUUIDWithCache(ctx, UUID)
		require.NoError(t, err)
		require.Equal(t, domain.Account{
			Username:  "testuser",
			UUID:      UUID,
			QueriedAt: now,
		}, account)

		// We should have hit the cache, so no calls to provider or repo
		require.False(t, provider.getAccountByUUIDCalled)
		require.False(t, repo.getAccountByUUIDCalled)
		require.False(t, repo.storeAccountCalled)
	})
}
