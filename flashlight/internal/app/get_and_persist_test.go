package app

import (
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/adapters/cache"
	"github.com/Amund211/flashlight/internal/adapters/playerprovider"
	"github.com/Amund211/flashlight/internal/adapters/playerrepository"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/domaintest"
)

const UUID = "01234567-89ab-cdef-0123-456789abcdef"

type panicPlayerProvider struct {
	t *testing.T
}

func (p *panicPlayerProvider) GetPlayer(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
	p.t.Helper()
	p.t.Fatal("should not be called")
	return nil, nil
}

type mockedPlayerProvider struct {
	t      *testing.T
	player *domain.PlayerPIT
	err    error
}

func (m *mockedPlayerProvider) GetPlayer(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
	m.t.Helper()

	require.Equal(m.t, UUID, uuid)

	return m.player, m.err
}

type stubAccountRepositoryByUUID struct {
	account domain.Account
	err     error
}

func (s stubAccountRepositoryByUUID) GetAccountByUUID(ctx context.Context, uuid string) (domain.Account, error) {
	return s.account, s.err
}

// fakePlayerRepository lets tests configure the result of GetPlayer and
// CountStats while inheriting the no-op behaviour of the stub repository for
// everything else.
type fakePlayerRepository struct {
	*playerrepository.StubPlayerRepository
	player       *domain.PlayerPIT
	getPlayerErr error
	statCount    int
}

func (f *fakePlayerRepository) GetPlayer(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
	if f.getPlayerErr != nil {
		return nil, f.getPlayerErr
	}
	return f.player, nil
}

func (f *fakePlayerRepository) CountStats(ctx context.Context, uuid string) (int, error) {
	return f.statCount, nil
}

type panicUserRepository struct {
	t *testing.T
}

func (p panicUserRepository) GetUser(ctx context.Context, userID string) (domain.User, error) {
	p.t.Helper()
	p.t.Fatal("GetUser should not be called")
	return domain.User{}, nil
}

type fakeUserRepository struct {
	user domain.User
	err  error
}

func (f fakeUserRepository) GetUser(ctx context.Context, userID string) (domain.User, error) {
	if f.err != nil {
		return domain.User{}, f.err
	}
	return f.user, nil
}

func TestGetAndPersistPlayer(t *testing.T) {
	t.Parallel()

	now := time.Now()

	mustBuildGetAndPersistPlayerWithCache := func(t *testing.T, cache cache.Cache[*domain.PlayerPIT], provider playerprovider.PlayerProvider) GetAndPersistPlayerWithCache {
		t.Helper()

		repo := playerrepository.NewStubPlayerRepository()
		accountRepo := stubAccountRepositoryByUUID{err: domain.ErrUsernameNotFound}
		getAccountByUUID := func(ctx context.Context, uuid string) (domain.Account, error) {
			return domain.Account{}, domain.ErrUsernameNotFound
		}

		usecase, err := BuildGetAndPersistPlayerWithCache(cache, provider, repo, accountRepo, getAccountByUUID, panicUserRepository{t: t}.GetUser)
		require.NoError(t, err)

		return usecase

	}
	t.Run("stats are not created if they already exist", func(t *testing.T) {
		t.Parallel()

		provider := &mockedPlayerProvider{
			t:      t,
			player: domaintest.NewPlayerBuilder(UUID).WithExperience(500).BuildPtr(now),
			err:    nil,
		}
		panicProvider := &panicPlayerProvider{t: t}
		cache := cache.NewBasicCache[*domain.PlayerPIT]()

		_, err := mustBuildGetAndPersistPlayerWithCache(t, cache, provider)(t.Context(), UUID, ProviderModeAlways, "")
		require.NoError(t, err)

		_, err = mustBuildGetAndPersistPlayerWithCache(t, cache, panicProvider)(t.Context(), UUID, ProviderModeAlways, "")
		require.NoError(t, err)
	})

	t.Run("provider errors are passed through", func(t *testing.T) {
		t.Parallel()

		for _, providerErr := range []error{
			domain.ErrPlayerNotFound,
			domain.ErrTemporarilyUnavailable,
		} {
			provider := &mockedPlayerProvider{
				t:      t,
				player: nil,
				err:    providerErr,
			}
			cache := cache.NewBasicCache[*domain.PlayerPIT]()

			_, err := mustBuildGetAndPersistPlayerWithCache(t, cache, provider)(t.Context(), "01234567-89ab-cdef-0123-456789abcdef", ProviderModeAlways, "")
			require.ErrorIs(t, err, providerErr)
		}
	})

	t.Run("invalid uuids should not be passed to get and persist with cache", func(t *testing.T) {
		t.Parallel()

		provider := &panicPlayerProvider{t: t}
		cache := cache.NewBasicCache[*domain.PlayerPIT]()

		for _, uuid := range []string{
			"",
			"invalid",
			"01234567-89ab-xxxx-0123-456789abcdef",
			"01234567-89ab-cdef-0123-456789abcde",
			"01234567-89ab-cdef-0123-456789abcdefg",
			"01234567-89ab-cdef-0123-456789abcdefg",
			"01234567-89ab-cdef-0123-456789abcdefg1234",
			"01---23456789aBCDef0123456789aBcdef",
		} {
			t.Run(fmt.Sprintf("UUID: '%s'", uuid), func(t *testing.T) {
				t.Parallel()

				_, err := mustBuildGetAndPersistPlayerWithCache(t, cache, provider)(t.Context(), uuid, ProviderModeAlways, "")
				require.Error(t, err)
			})
		}
	})
}

func TestUpdatePlayerInInterval(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name         string
		start        time.Time
		end          time.Time
		now          time.Time
		shouldUpdate bool
	}{
		{
			name:         "current interval",
			start:        time.Date(2024, time.March, 12, 0, 0, 0, 0, time.UTC),
			end:          time.Date(2024, time.March, 26, 23, 59, 59, 999_999_999, time.UTC),
			now:          time.Date(2024, time.March, 17, 12, 0, 0, 0, time.UTC),
			shouldUpdate: true,
		},
		{
			name:         "interval in the past",
			start:        time.Date(2023, time.January, 1, 0, 0, 0, 0, time.UTC),
			end:          time.Date(2023, time.January, 2, 0, 0, 0, 0, time.UTC),
			now:          time.Date(2023, time.January, 3, 0, 0, 0, 0, time.UTC),
			shouldUpdate: false,
		},
		{
			name:         "interval in the future",
			start:        time.Date(2023, time.January, 12, 0, 0, 0, 0, time.UTC),
			end:          time.Date(2023, time.January, 13, 0, 0, 0, 0, time.UTC),
			now:          time.Date(2023, time.January, 1, 0, 0, 0, 0, time.UTC),
			shouldUpdate: false,
		},
		{
			name:         "start=now",
			start:        time.Date(2023, time.January, 1, 0, 0, 0, 0, time.UTC),
			end:          time.Date(2023, time.January, 2, 0, 0, 0, 0, time.UTC),
			now:          time.Date(2023, time.January, 1, 0, 0, 0, 0, time.UTC),
			shouldUpdate: true,
		},
		{
			name:  "end=now",
			start: time.Date(2023, time.January, 1, 0, 0, 0, 0, time.UTC),
			end:   time.Date(2023, time.January, 2, 0, 0, 0, 0, time.UTC),
			now:   time.Date(2023, time.January, 2, 0, 0, 0, 0, time.UTC),
			// NOTE: Not really any point in updating, as the time will be outside the interval by the time the new stats come in
			shouldUpdate: true,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			testUUID := "01234567-9999-9999-0123-456789abcdef"

			updated := false
			getAndPersist := func(ctx context.Context, uuid string, providerMode ProviderMode, requesterUserID string) (*domain.PlayerPIT, error) {
				t.Helper()
				require.Equal(t, testUUID, uuid)
				require.Equal(t, ProviderModeAlways, providerMode)
				require.Empty(t, requesterUserID)
				updated = true
				return nil, nil
			}

			updatePlayerInInterval := BuildUpdatePlayerInInterval(getAndPersist, func() time.Time { return tc.now })

			err := updatePlayerInInterval(t.Context(), testUUID, tc.start, tc.end)
			require.NoError(t, err)

			require.Equal(t, tc.shouldUpdate, updated)
		})
	}

	t.Run("getAndPersist errors", func(t *testing.T) {
		t.Parallel()

		now := time.Now()
		start := now.Add(-time.Hour)
		end := now.Add(time.Hour)

		testUUID := "01234567-0000-9999-0123-456789abcdef"

		called := false
		getAndPersist := func(ctx context.Context, uuid string, providerMode ProviderMode, requesterUserID string) (*domain.PlayerPIT, error) {
			t.Helper()
			require.Equal(t, testUUID, uuid)
			require.Equal(t, ProviderModeAlways, providerMode)
			require.Empty(t, requesterUserID)
			called = true
			return nil, assert.AnError
		}

		updatePlayerInInterval := BuildUpdatePlayerInInterval(getAndPersist, func() time.Time { return now })

		err := updatePlayerInInterval(t.Context(), testUUID, start, end)
		require.ErrorIs(t, err, assert.AnError)

		require.True(t, called)
	})
}

func TestGetAndPersistPlayerProviderMode(t *testing.T) {
	t.Parallel()

	now := time.Now()

	buildWithGetUser := func(
		t *testing.T,
		provider playerprovider.PlayerProvider,
		repo playerrepository.PlayerRepository,
		accountRepo displaynameAccountRepository,
		getAccountByUUID GetAccountByUUID,
		getUser GetUser,
	) GetAndPersistPlayerWithCache {
		t.Helper()
		usecase, err := BuildGetAndPersistPlayerWithCache(
			cache.NewBasicCache[*domain.PlayerPIT](),
			provider,
			repo,
			accountRepo,
			getAccountByUUID,
			getUser,
		)
		require.NoError(t, err)
		return usecase
	}

	build := func(
		t *testing.T,
		provider playerprovider.PlayerProvider,
		repo playerrepository.PlayerRepository,
		accountRepo displaynameAccountRepository,
		getAccountByUUID GetAccountByUUID,
	) GetAndPersistPlayerWithCache {
		t.Helper()
		return buildWithGetUser(t, provider, repo, accountRepo, getAccountByUUID, panicUserRepository{t: t}.GetUser)
	}

	panicGetAccount := func(t *testing.T) GetAccountByUUID {
		return func(ctx context.Context, uuid string) (domain.Account, error) {
			t.Helper()
			t.Fatal("getAccountByUUID should not be called")
			return domain.Account{}, nil
		}
	}

	t.Run("fallback returns stored player without querying the provider", func(t *testing.T) {
		t.Parallel()

		repo := &fakePlayerRepository{
			StubPlayerRepository: playerrepository.NewStubPlayerRepository(),
			player:               domaintest.NewPlayerBuilder(UUID).WithExperience(1234).BuildPtr(now),
		}
		accountRepo := stubAccountRepositoryByUUID{account: domain.Account{UUID: UUID, Username: "StoredName"}}

		usecase := build(t, &panicPlayerProvider{t: t}, repo, accountRepo, panicGetAccount(t))

		player, err := usecase(t.Context(), UUID, ProviderModeFallback, "")
		require.NoError(t, err)
		require.NotNil(t, player)
		require.Equal(t, int64(1234), player.Experience)
		require.NotNil(t, player.Displayname)
		require.Equal(t, "StoredName", *player.Displayname)
	})

	t.Run("fallback resolves username via provider when not in account repo", func(t *testing.T) {
		t.Parallel()

		repo := &fakePlayerRepository{
			StubPlayerRepository: playerrepository.NewStubPlayerRepository(),
			player:               domaintest.NewPlayerBuilder(UUID).WithExperience(1234).BuildPtr(now),
		}
		accountRepo := stubAccountRepositoryByUUID{err: domain.ErrUsernameNotFound}
		getAccountByUUID := func(ctx context.Context, uuid string) (domain.Account, error) {
			return domain.Account{UUID: UUID, Username: "FetchedName"}, nil
		}

		usecase := build(t, &panicPlayerProvider{t: t}, repo, accountRepo, getAccountByUUID)

		player, err := usecase(t.Context(), UUID, ProviderModeFallback, "")
		require.NoError(t, err)
		require.NotNil(t, player.Displayname)
		require.Equal(t, "FetchedName", *player.Displayname)
	})

	t.Run("fallback queries the provider when there are no stored stats", func(t *testing.T) {
		t.Parallel()

		repo := &fakePlayerRepository{
			StubPlayerRepository: playerrepository.NewStubPlayerRepository(),
			getPlayerErr:         domain.ErrPlayerNotFound,
		}
		provider := &mockedPlayerProvider{
			t:      t,
			player: domaintest.NewPlayerBuilder(UUID).WithExperience(999).BuildPtr(now),
		}
		accountRepo := stubAccountRepositoryByUUID{err: domain.ErrUsernameNotFound}

		usecase := build(t, provider, repo, accountRepo, panicGetAccount(t))

		player, err := usecase(t.Context(), UUID, ProviderModeFallback, "")
		require.NoError(t, err)
		require.Equal(t, int64(999), player.Experience)
	})

	t.Run("never returns stored player without querying the provider", func(t *testing.T) {
		t.Parallel()

		repo := &fakePlayerRepository{
			StubPlayerRepository: playerrepository.NewStubPlayerRepository(),
			player:               domaintest.NewPlayerBuilder(UUID).WithExperience(1234).BuildPtr(now),
		}
		accountRepo := stubAccountRepositoryByUUID{account: domain.Account{UUID: UUID, Username: "StoredName"}}

		usecase := build(t, &panicPlayerProvider{t: t}, repo, accountRepo, panicGetAccount(t))

		player, err := usecase(t.Context(), UUID, ProviderModeNever, "")
		require.NoError(t, err)
		require.Equal(t, int64(1234), player.Experience)
		require.NotNil(t, player.Displayname)
		require.Equal(t, "StoredName", *player.Displayname)
	})

	t.Run("never fails without querying the provider when no stored stats", func(t *testing.T) {
		t.Parallel()

		repo := &fakePlayerRepository{
			StubPlayerRepository: playerrepository.NewStubPlayerRepository(),
			getPlayerErr:         domain.ErrPlayerNotFound,
		}
		accountRepo := stubAccountRepositoryByUUID{err: domain.ErrUsernameNotFound}

		usecase := build(t, &panicPlayerProvider{t: t}, repo, accountRepo, panicGetAccount(t))

		_, err := usecase(t.Context(), UUID, ProviderModeNever, "")
		require.Error(t, err)
		// Must NOT be ErrPlayerNotFound so the port responds with 500, not 404.
		require.NotErrorIs(t, err, domain.ErrPlayerNotFound)
	})

	t.Run("well-known queries the provider when the player has enough stored stats", func(t *testing.T) {
		t.Parallel()

		repo := &fakePlayerRepository{
			StubPlayerRepository: playerrepository.NewStubPlayerRepository(),
			// Stored player is stale; well-known should ignore it and query the provider.
			player:    domaintest.NewPlayerBuilder(UUID).WithExperience(1234).BuildPtr(now),
			statCount: wellKnownStatsThreshold,
		}
		provider := &mockedPlayerProvider{
			t:      t,
			player: domaintest.NewPlayerBuilder(UUID).WithExperience(999).BuildPtr(now),
		}
		accountRepo := stubAccountRepositoryByUUID{err: domain.ErrUsernameNotFound}

		usecase := build(t, provider, repo, accountRepo, panicGetAccount(t))

		player, err := usecase(t.Context(), UUID, ProviderModeWellKnown, "")
		require.NoError(t, err)
		require.Equal(t, int64(999), player.Experience)
	})

	t.Run("well-known returns stored player without querying the provider when below threshold", func(t *testing.T) {
		t.Parallel()

		repo := &fakePlayerRepository{
			StubPlayerRepository: playerrepository.NewStubPlayerRepository(),
			player:               domaintest.NewPlayerBuilder(UUID).WithExperience(1234).BuildPtr(now),
			statCount:            wellKnownStatsThreshold - 1,
		}
		accountRepo := stubAccountRepositoryByUUID{account: domain.Account{UUID: UUID, Username: "StoredName"}}

		usecase := build(t, &panicPlayerProvider{t: t}, repo, accountRepo, panicGetAccount(t))

		player, err := usecase(t.Context(), UUID, ProviderModeWellKnown, "")
		require.NoError(t, err)
		require.Equal(t, int64(1234), player.Experience)
		require.NotNil(t, player.Displayname)
		require.Equal(t, "StoredName", *player.Displayname)
	})

	t.Run("well-known fails without querying the provider when below threshold and no stored stats", func(t *testing.T) {
		t.Parallel()

		repo := &fakePlayerRepository{
			StubPlayerRepository: playerrepository.NewStubPlayerRepository(),
			getPlayerErr:         domain.ErrPlayerNotFound,
			statCount:            0,
		}
		accountRepo := stubAccountRepositoryByUUID{err: domain.ErrUsernameNotFound}

		usecase := build(t, &panicPlayerProvider{t: t}, repo, accountRepo, panicGetAccount(t))

		_, err := usecase(t.Context(), UUID, ProviderModeWellKnown, "")
		require.Error(t, err)
		// Must NOT be ErrPlayerNotFound so the port responds with 500, not 404.
		require.NotErrorIs(t, err, domain.ErrPlayerNotFound)
	})

	t.Run("invalid provider mode errors without querying anything", func(t *testing.T) {
		t.Parallel()

		repo := &fakePlayerRepository{StubPlayerRepository: playerrepository.NewStubPlayerRepository()}
		accountRepo := stubAccountRepositoryByUUID{err: domain.ErrUsernameNotFound}

		usecase := build(t, &panicPlayerProvider{t: t}, repo, accountRepo, panicGetAccount(t))

		_, err := usecase(t.Context(), UUID, ProviderMode("bogus"), "")
		require.Error(t, err)
	})

	t.Run("well-known queries the provider when the requester was first seen before the cutoff", func(t *testing.T) {
		t.Parallel()

		repo := &fakePlayerRepository{
			StubPlayerRepository: playerrepository.NewStubPlayerRepository(),
			// Requested player is not well-known; the well-known requester
			// should still get fresh data from the provider.
			player:    domaintest.NewPlayerBuilder(UUID).WithExperience(1234).BuildPtr(now),
			statCount: 0,
		}
		provider := &mockedPlayerProvider{
			t:      t,
			player: domaintest.NewPlayerBuilder(UUID).WithExperience(999).BuildPtr(now),
		}
		accountRepo := stubAccountRepositoryByUUID{err: domain.ErrUsernameNotFound}
		userRepo := fakeUserRepository{
			user: domain.User{UserID: "requester-1", FirstSeenAt: wellKnownUserFirstSeenCutoff.Add(-time.Hour)},
		}

		usecase := buildWithGetUser(t, provider, repo, accountRepo, panicGetAccount(t), userRepo.GetUser)

		player, err := usecase(t.Context(), UUID, ProviderModeWellKnown, "requester-1")
		require.NoError(t, err)
		require.Equal(t, int64(999), player.Experience)
	})

	t.Run("well-known ignores requesters with too many visits", func(t *testing.T) {
		t.Parallel()

		for _, seenCount := range []int64{
			wellKnownUserMaxSeenCount,
			wellKnownUserMaxSeenCount + 1,
		} {
			repo := &fakePlayerRepository{
				StubPlayerRepository: playerrepository.NewStubPlayerRepository(),
				player:               domaintest.NewPlayerBuilder(UUID).WithExperience(1234).BuildPtr(now),
				statCount:            wellKnownStatsThreshold - 1,
			}
			accountRepo := stubAccountRepositoryByUUID{account: domain.Account{UUID: UUID, Username: "StoredName"}}
			userRepo := fakeUserRepository{
				user: domain.User{
					UserID:      "requester-1",
					FirstSeenAt: wellKnownUserFirstSeenCutoff.Add(-time.Hour),
					SeenCount:   seenCount,
				},
			}

			usecase := buildWithGetUser(t, &panicPlayerProvider{t: t}, repo, accountRepo, panicGetAccount(t), userRepo.GetUser)

			player, err := usecase(t.Context(), UUID, ProviderModeWellKnown, "requester-1")
			require.NoError(t, err)
			require.Equal(t, int64(1234), player.Experience)
		}
	})

	t.Run("well-known accepts requesters just below the visit limit", func(t *testing.T) {
		t.Parallel()

		repo := &fakePlayerRepository{
			StubPlayerRepository: playerrepository.NewStubPlayerRepository(),
			player:               domaintest.NewPlayerBuilder(UUID).WithExperience(1234).BuildPtr(now),
			statCount:            0,
		}
		provider := &mockedPlayerProvider{
			t:      t,
			player: domaintest.NewPlayerBuilder(UUID).WithExperience(999).BuildPtr(now),
		}
		accountRepo := stubAccountRepositoryByUUID{err: domain.ErrUsernameNotFound}
		userRepo := fakeUserRepository{
			user: domain.User{
				UserID:      "requester-1",
				FirstSeenAt: wellKnownUserFirstSeenCutoff.Add(-time.Hour),
				SeenCount:   wellKnownUserMaxSeenCount - 1,
			},
		}

		usecase := buildWithGetUser(t, provider, repo, accountRepo, panicGetAccount(t), userRepo.GetUser)

		player, err := usecase(t.Context(), UUID, ProviderModeWellKnown, "requester-1")
		require.NoError(t, err)
		require.Equal(t, int64(999), player.Experience)
	})

	t.Run("well-known returns stored player when the requester was first seen at or after the cutoff", func(t *testing.T) {
		t.Parallel()

		for _, firstSeen := range []time.Time{
			wellKnownUserFirstSeenCutoff,
			wellKnownUserFirstSeenCutoff.Add(time.Hour),
		} {
			repo := &fakePlayerRepository{
				StubPlayerRepository: playerrepository.NewStubPlayerRepository(),
				player:               domaintest.NewPlayerBuilder(UUID).WithExperience(1234).BuildPtr(now),
				statCount:            wellKnownStatsThreshold - 1,
			}
			accountRepo := stubAccountRepositoryByUUID{account: domain.Account{UUID: UUID, Username: "StoredName"}}
			userRepo := fakeUserRepository{
				user: domain.User{UserID: "requester-1", FirstSeenAt: firstSeen},
			}

			usecase := buildWithGetUser(t, &panicPlayerProvider{t: t}, repo, accountRepo, panicGetAccount(t), userRepo.GetUser)

			player, err := usecase(t.Context(), UUID, ProviderModeWellKnown, "requester-1")
			require.NoError(t, err)
			require.Equal(t, int64(1234), player.Experience)
		}
	})

	t.Run("well-known does not look up the requester when no user id is given", func(t *testing.T) {
		t.Parallel()

		repo := &fakePlayerRepository{
			StubPlayerRepository: playerrepository.NewStubPlayerRepository(),
			player:               domaintest.NewPlayerBuilder(UUID).WithExperience(1234).BuildPtr(now),
			statCount:            wellKnownStatsThreshold - 1,
		}
		accountRepo := stubAccountRepositoryByUUID{account: domain.Account{UUID: UUID, Username: "StoredName"}}

		// The panicking user repository ensures we never look up an empty user id.
		usecase := build(t, &panicPlayerProvider{t: t}, repo, accountRepo, panicGetAccount(t))

		player, err := usecase(t.Context(), UUID, ProviderModeWellKnown, "")
		require.NoError(t, err)
		require.Equal(t, int64(1234), player.Experience)
	})

	t.Run("well-known treats unknown requesters as not well-known", func(t *testing.T) {
		t.Parallel()

		repo := &fakePlayerRepository{
			StubPlayerRepository: playerrepository.NewStubPlayerRepository(),
			player:               domaintest.NewPlayerBuilder(UUID).WithExperience(1234).BuildPtr(now),
			statCount:            wellKnownStatsThreshold - 1,
		}
		accountRepo := stubAccountRepositoryByUUID{account: domain.Account{UUID: UUID, Username: "StoredName"}}
		userRepo := fakeUserRepository{err: domain.ErrUserNotFound}

		usecase := buildWithGetUser(t, &panicPlayerProvider{t: t}, repo, accountRepo, panicGetAccount(t), userRepo.GetUser)

		player, err := usecase(t.Context(), UUID, ProviderModeWellKnown, "requester-1")
		require.NoError(t, err)
		require.Equal(t, int64(1234), player.Experience)
	})

	t.Run("well-known treats requester lookup failures as not well-known", func(t *testing.T) {
		t.Parallel()

		repo := &fakePlayerRepository{
			StubPlayerRepository: playerrepository.NewStubPlayerRepository(),
			player:               domaintest.NewPlayerBuilder(UUID).WithExperience(1234).BuildPtr(now),
			statCount:            wellKnownStatsThreshold - 1,
		}
		accountRepo := stubAccountRepositoryByUUID{account: domain.Account{UUID: UUID, Username: "StoredName"}}
		userRepo := fakeUserRepository{err: assert.AnError}

		usecase := buildWithGetUser(t, &panicPlayerProvider{t: t}, repo, accountRepo, panicGetAccount(t), userRepo.GetUser)

		player, err := usecase(t.Context(), UUID, ProviderModeWellKnown, "requester-1")
		require.NoError(t, err)
		require.Equal(t, int64(1234), player.Experience)
	})

	t.Run("requester is not looked up for other provider modes", func(t *testing.T) {
		t.Parallel()

		repo := &fakePlayerRepository{StubPlayerRepository: playerrepository.NewStubPlayerRepository()}
		provider := &mockedPlayerProvider{
			t:      t,
			player: domaintest.NewPlayerBuilder(UUID).WithExperience(999).BuildPtr(now),
		}
		accountRepo := stubAccountRepositoryByUUID{err: domain.ErrUsernameNotFound}

		usecase := build(t, provider, repo, accountRepo, panicGetAccount(t))

		player, err := usecase(t.Context(), UUID, ProviderModeAlways, "requester-1")
		require.NoError(t, err)
		require.Equal(t, int64(999), player.Experience)
	})

	t.Run("well-known requester results are not served to other requesters from the cache", func(t *testing.T) {
		t.Parallel()

		sharedCache := cache.NewBasicCache[*domain.PlayerPIT]()
		accountRepo := stubAccountRepositoryByUUID{account: domain.Account{UUID: UUID, Username: "StoredName"}}

		buildShared := func(t *testing.T, provider playerprovider.PlayerProvider, getUser GetUser) GetAndPersistPlayerWithCache {
			t.Helper()
			repo := &fakePlayerRepository{
				StubPlayerRepository: playerrepository.NewStubPlayerRepository(),
				player:               domaintest.NewPlayerBuilder(UUID).WithExperience(1234).BuildPtr(now),
				statCount:            wellKnownStatsThreshold - 1,
			}
			usecase, err := BuildGetAndPersistPlayerWithCache(
				sharedCache,
				provider,
				repo,
				accountRepo,
				panicGetAccount(t),
				getUser,
			)
			require.NoError(t, err)
			return usecase
		}

		wellKnownRequesterUsecase := buildShared(
			t,
			&mockedPlayerProvider{t: t, player: domaintest.NewPlayerBuilder(UUID).WithExperience(999).BuildPtr(now)},
			fakeUserRepository{user: domain.User{UserID: "requester-1", FirstSeenAt: wellKnownUserFirstSeenCutoff.Add(-time.Hour)}}.GetUser,
		)

		player, err := wellKnownRequesterUsecase(t.Context(), UUID, ProviderModeWellKnown, "requester-1")
		require.NoError(t, err)
		require.Equal(t, int64(999), player.Experience)

		// An anonymous requester asking for the same (not well-known) player
		// must not be served the well-known requester's fresh data.
		anonymousUsecase := buildShared(t, &panicPlayerProvider{t: t}, panicUserRepository{t: t}.GetUser)

		player, err = anonymousUsecase(t.Context(), UUID, ProviderModeWellKnown, "")
		require.NoError(t, err)
		require.Equal(t, int64(1234), player.Experience)
	})
}
