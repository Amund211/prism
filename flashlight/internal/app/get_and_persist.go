package app

import (
	"context"
	"errors"
	"fmt"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"

	"github.com/Amund211/flashlight/internal/adapters/cache"
	"github.com/Amund211/flashlight/internal/adapters/playerprovider"
	"github.com/Amund211/flashlight/internal/adapters/playerrepository"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
)

// ProviderMode controls how GetAndPersistPlayerWithCache sources player data.
type ProviderMode string

const (
	// ProviderModeAlways always queries the player provider (Hypixel) for fresh
	// data and persists it. This is the original behaviour.
	ProviderModeAlways ProviderMode = "always"
	// ProviderModeFallback returns the most recent stored stats when we have
	// them, only querying the provider when we have no stored stats for the
	// player.
	ProviderModeFallback ProviderMode = "fallback"
	// ProviderModeNever never queries the provider. If we have no stored stats
	// for the player the request fails.
	ProviderModeNever ProviderMode = "never"
	// ProviderModeWellKnown behaves like ProviderModeAlways when either the
	// requested player or the requesting user is well-known, and like
	// ProviderModeNever otherwise. A requested player is well-known when they
	// have at least wellKnownStatsThreshold stored stat records; a requesting
	// user is well-known when we first saw their user ID before
	// wellKnownUserFirstSeenCutoff and they have fewer than
	// wellKnownUserMaxSeenCount visits.
	ProviderModeWellKnown ProviderMode = "well-known"
)

// wellKnownStatsThreshold is the minimum number of stored stat records a player
// must have for ProviderModeWellKnown to treat them as well-known and query the
// provider for fresh data.
const wellKnownStatsThreshold = 40

// wellKnownUserFirstSeenCutoff is the first seen cutoff for requesting users in
// ProviderModeWellKnown: users first seen before this time are considered
// well-known and get fresh data from the provider for any requested player.
// The cutoff sits just before the first spike in created users in the live db
// and marks 516 user ids as well-known (one day later it would be 1376).
var wellKnownUserFirstSeenCutoff = time.Date(2026, time.March, 1, 0, 0, 0, 0, time.UTC)

// wellKnownUserMaxSeenCount excludes "well-known spammers" from the requesting
// user check in ProviderModeWellKnown: users seen this many times or more are
// not considered well-known even if they were first seen before the cutoff.
const wellKnownUserMaxSeenCount = 30_000

// wellKnownProviderChance is the probability that a ProviderModeWellKnown
// request queries the provider for fresh data regardless of whether the player
// is well-known. The roll happens before the well-known checks, so it applies
// to every ProviderModeWellKnown request, not just the ones we would otherwise
// reject - a losing roll falls back to the normal well-known behaviour.
//
// NOTE: This is a per-request chance, and we reject unservable requests with a
// retryable status, so the chance that a rejected client eventually gets served
// is much higher than this: prism retries up to 5 times, giving 1-0.7^5 ~= 83%.
const wellKnownProviderChance = 0.3

func (m ProviderMode) validate() error {
	switch m {
	case ProviderModeAlways, ProviderModeFallback, ProviderModeNever, ProviderModeWellKnown:
		return nil
	default:
		return fmt.Errorf("invalid provider mode: %q", string(m))
	}
}

// GetAndPersistPlayerWithCache returns player data for the given (player) uuid.
// requesterUserID identifies the user making the request (empty when unknown);
// it is only used by ProviderModeWellKnown.
type GetAndPersistPlayerWithCache func(ctx context.Context, uuid string, providerMode ProviderMode, requesterUserID string) (*domain.PlayerPIT, error)

// displaynameAccountRepository resolves a username from our own account store.
// The player stats repository does not store usernames, so we resolve them
// separately when serving stats from the repository.
type displaynameAccountRepository interface {
	GetAccountByUUID(ctx context.Context, uuid string) (domain.Account, error)
}

type getAndPersistPlayerMetricsCollection struct {
	returnCount metric.Int64Counter
}

func setupGetAndPersistPlayerMetrics(meter metric.Meter) (getAndPersistPlayerMetricsCollection, error) {
	returnCount, err := meter.Int64Counter("app/get_and_persist_player/return_count")
	if err != nil {
		return getAndPersistPlayerMetricsCollection{}, fmt.Errorf("failed to create return count metric: %w", err)
	}

	return getAndPersistPlayerMetricsCollection{
		returnCount: returnCount,
	}, nil
}

func getAndPersistPlayerWithoutCache(ctx context.Context, provider playerprovider.PlayerProvider, repo playerrepository.PlayerRepository, uuid string) (*domain.PlayerPIT, error) {
	getCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	player, err := provider.GetPlayer(getCtx, uuid)
	if err != nil {
		// NOTE: PlayerProvider implementations handle their own error reporting
		return nil, fmt.Errorf("could not get player: %w", err)
	}

	// Ignore cancellations from the request context and try to store the data anyway
	// Take a maximum of 1 second to not block the request for too long
	storeCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 1*time.Second)
	defer cancel()
	err = repo.StorePlayer(storeCtx, player)
	if err != nil {
		// NOTE: PlayerRepository implementations handle their own error reporting
		logging.FromContext(ctx).ErrorContext(ctx, "failed to store player", "error", err.Error())

		// NOTE: We still return the player to fulfill the request even though storing failed
	}

	return player, nil
}

func BuildGetAndPersistPlayerWithCache(
	playerCache cache.Cache[*domain.PlayerPIT],
	provider playerprovider.PlayerProvider,
	repo playerrepository.PlayerRepository,
	accountRepo displaynameAccountRepository,
	getAccountByUUID GetAccountByUUID,
	getUser GetUser,
	// randFloat returns a random float in [0, 1) and decides whether a
	// ProviderModeWellKnown request that would otherwise fail queries the
	// provider anyway. Tests pass a deterministic implementation.
	randFloat func() float64,
) (GetAndPersistPlayerWithCache, error) {
	const name = "flashlight/app/get_and_persist_player_with_cache"

	meter := otel.Meter(name)

	metrics, err := setupGetAndPersistPlayerMetrics(meter)
	if err != nil {
		return nil, fmt.Errorf("failed to set up metrics: %w", err)
	}

	type trackingInfo struct {
		success      bool
		found        bool
		cached       bool
		invalidInput bool
		providerMode ProviderMode
	}

	track := func(ctx context.Context, info trackingInfo) {
		metrics.returnCount.Add(
			ctx,
			1,
			metric.WithAttributes(
				attribute.Bool("success", info.success),
				attribute.Bool("found", info.found),
				attribute.Bool("cached", info.cached),
				attribute.Bool("invalid_input", info.invalidInput),
				attribute.String("provider_mode", string(info.providerMode)),
			),
		)
	}

	// resolveDisplayname resolves a player's current username. The stats
	// repository does not store usernames, so when we serve stats from the
	// repository we resolve the name separately. We check our own account store
	// first and only query the provider when we don't have it stored.
	resolveDisplayname := func(ctx context.Context, uuid string) *string {
		account, err := accountRepo.GetAccountByUUID(ctx, uuid)
		if err != nil {
			// Not stored (or lookup failed) -> resolve via the account use case,
			// which queries the provider and persists the result.
			// NOTE: accountRepo / getAccountByUUID handle their own error reporting.
			account, err = getAccountByUUID(ctx, uuid)
			if err != nil {
				// The username is non-critical -> return the stats without it.
				logging.FromContext(ctx).WarnContext(ctx, "Failed to resolve username for repository player", "uuid", uuid, "error", err.Error())
				return nil
			}
		}
		username := account.Username
		return &username
	}

	// getStoredPlayerOrFail returns the most recent stored stats for the player
	// without ever querying the provider. If we have no stored stats it returns
	// a generic error (not ErrPlayerNotFound) so the caller responds with a 500
	// rather than a 404.
	getStoredPlayerOrFail := func(ctx context.Context, uuid string, providerMode ProviderMode) (*domain.PlayerPIT, error) {
		repoPlayer, err := repo.GetPlayer(ctx, uuid)
		if err == nil {
			repoPlayer.Displayname = resolveDisplayname(ctx, uuid)
			return repoPlayer, nil
		}
		if errors.Is(err, domain.ErrPlayerNotFound) {
			return nil, fmt.Errorf("player not stored and provider mode is %q", providerMode)
		}
		// NOTE: PlayerRepository implementations handle their own error reporting
		return nil, fmt.Errorf("failed to get player from repository: %w", err)
	}

	// requesterIsWellKnown reports whether the requesting user was first seen
	// before wellKnownUserFirstSeenCutoff and has fewer than
	// wellKnownUserMaxSeenCount visits. Unknown users and lookup failures are
	// treated as not well-known.
	requesterIsWellKnown := func(ctx context.Context, requesterUserID string) bool {
		if requesterUserID == "" {
			return false
		}
		user, err := getUser(ctx, requesterUserID)
		if err != nil {
			if !errors.Is(err, domain.ErrUserNotFound) {
				// NOTE: GetUser implementations handle their own error reporting
				logging.FromContext(ctx).WarnContext(ctx, "Failed to get requesting user, treating them as not well-known", "error", err.Error())
			}
			return false
		}
		return user.FirstSeenAt.Before(wellKnownUserFirstSeenCutoff) && user.SeenCount < wellKnownUserMaxSeenCount
	}

	return func(ctx context.Context, uuid string, providerMode ProviderMode, requesterUserID string) (*domain.PlayerPIT, error) {
		if err := providerMode.validate(); err != nil {
			logging.FromContext(ctx).ErrorContext(ctx, "Invalid provider mode", "providerMode", string(providerMode))
			reporting.Report(ctx, err, map[string]string{
				"providerMode": string(providerMode),
			})
			track(ctx, trackingInfo{success: false, invalidInput: true, providerMode: "invalid"})
			return nil, err
		}

		if !strutils.UUIDIsNormalized(uuid) {
			logging.FromContext(ctx).ErrorContext(ctx, "UUID is not normalized", "uuid", uuid)
			err := fmt.Errorf("UUID is not normalized")
			reporting.Report(ctx, err)
			track(ctx, trackingInfo{success: false, invalidInput: true, providerMode: providerMode})
			return nil, err
		}

		effectiveProviderMode := providerMode
		if providerMode == ProviderModeWellKnown && requesterIsWellKnown(ctx, requesterUserID) {
			// Well-known requesting user -> get fresh data regardless of the
			// requested player.
			logging.FromContext(ctx).InfoContext(ctx, "Requesting user is well-known, getting fresh data")
			effectiveProviderMode = ProviderModeAlways
		}

		// Include the (effective) provider mode in the cache key so requests
		// with different modes don't serve each other's (differently-sourced)
		// results.
		cacheKey := string(effectiveProviderMode) + ":" + uuid

		player, created, err := cache.GetOrCreate(ctx, playerCache, cacheKey, func() (*domain.PlayerPIT, error) {
			switch effectiveProviderMode {
			case ProviderModeAlways:
				return getAndPersistPlayerWithoutCache(ctx, provider, repo, uuid)
			case ProviderModeFallback:
				repoPlayer, err := repo.GetPlayer(ctx, uuid)
				if err == nil {
					repoPlayer.Displayname = resolveDisplayname(ctx, uuid)
					return repoPlayer, nil
				}
				if !errors.Is(err, domain.ErrPlayerNotFound) {
					// NOTE: PlayerRepository implementations handle their own error reporting
					logging.FromContext(ctx).WarnContext(ctx, "Failed to read player from repository, falling back to provider", "error", err.Error())
				}
				// No stored stats (or lookup failed) -> fetch from the provider
				return getAndPersistPlayerWithoutCache(ctx, provider, repo, uuid)
			case ProviderModeNever:
				// Provider mode is never -> we don't query the provider.
				return getStoredPlayerOrFail(ctx, uuid, providerMode)
			case ProviderModeWellKnown:
				// Roll before the well-known checks: a winning roll gets fresh
				// data for any player, so below-threshold players keep accruing
				// records towards wellKnownStatsThreshold instead of being
				// frozen at whatever snapshot we happen to have stored.
				if randFloat() < wellKnownProviderChance {
					logging.FromContext(ctx).InfoContext(ctx, "Well-known provider roll won, getting fresh data")
					return getAndPersistPlayerWithoutCache(ctx, provider, repo, uuid)
				}
				count, err := repo.CountStats(ctx, uuid)
				if err != nil {
					// NOTE: PlayerRepository implementations handle their own error reporting
					return nil, fmt.Errorf("failed to count stored player stats: %w", err)
				}
				logging.FromContext(ctx).InfoContext(ctx, "Counted stored player stats for well-known provider mode", "statsCount", count)
				if count >= wellKnownStatsThreshold {
					// Well-known player -> behave like ProviderModeAlways.
					return getAndPersistPlayerWithoutCache(ctx, provider, repo, uuid)
				}
				// Not well-known and the roll lost -> behave like
				// ProviderModeNever.
				storedPlayer, err := getStoredPlayerOrFail(ctx, uuid, providerMode)
				if err == nil {
					return storedPlayer, nil
				}
				// We have nothing to serve this requester. Report the rejection
				// as temporarily unavailable (504) so prism retries it.
				// Failures aren't cached, so every retry re-rolls.
				return nil, fmt.Errorf("%w: %w", domain.ErrTemporarilyUnavailable, err)
			default:
				// Unreachable: providerMode was validated above.
				return nil, fmt.Errorf("invalid provider mode: %q", providerMode)
			}
		})
		if err != nil {
			// NOTE: The error is either create()'s — the create functions
			// handle their own error reporting — or GetOrCreate giving up on a
			// done context or a contended entry, which it logs itself.
			if errors.Is(err, domain.ErrPlayerNotFound) {
				track(ctx, trackingInfo{success: true, found: false, providerMode: providerMode})
			} else {
				track(ctx, trackingInfo{success: false, providerMode: providerMode})
			}
			return nil, fmt.Errorf("failed to cache.GetOrCreate player data: %w", err)
		}

		track(ctx, trackingInfo{success: true, found: true, cached: !created, providerMode: providerMode})
		return player, nil
	}, nil
}

// Ensure that the player data is up to date in the repository in the given interval.
type UpdatePlayerInInterval func(ctx context.Context, uuid string, start, end time.Time) error

func BuildUpdatePlayerInInterval(
	getAndPersistPlayerWithCache GetAndPersistPlayerWithCache,
	nowFunc func() time.Time,
) UpdatePlayerInInterval {
	return func(ctx context.Context, uuid string, start, end time.Time) error {
		if !strutils.UUIDIsNormalized(uuid) {
			err := fmt.Errorf("UUID is not normalized")
			reporting.Report(ctx, err)
			return err
		}

		if start.After(end) {
			err := fmt.Errorf("start time is after end time")
			reporting.Report(ctx, err)
			return err
		}

		now := nowFunc()

		if start.After(now) {
			// The interval is in the future, getting and persisting player data will not affect it
			return nil
		}

		if end.Before(now) {
			// The interval is in the past, getting and persisting player data will not affect it
			return nil
		}

		// This is a current interval -> fetch new data and persist it to the repository
		_, err := getAndPersistPlayerWithCache(ctx, uuid, ProviderModeAlways, "")
		if err != nil {
			// NOTE: GetAndPersistPlayerWithCache implementations handle their own error reporting
			return fmt.Errorf("failed to get updated player data: %w", err)
		}

		return nil
	}
}
