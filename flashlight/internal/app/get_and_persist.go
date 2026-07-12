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
	// ProviderModeWellKnown behaves like ProviderModeAlways for players we
	// consider well-known (those with at least wellKnownStatsThreshold stored
	// stat records) and like ProviderModeNever for everyone else.
	ProviderModeWellKnown ProviderMode = "well-known"
)

// wellKnownStatsThreshold is the minimum number of stored stat records a player
// must have for ProviderModeWellKnown to treat them as well-known and query the
// provider for fresh data.
const wellKnownStatsThreshold = 40

func (m ProviderMode) validate() error {
	switch m {
	case ProviderModeAlways, ProviderModeFallback, ProviderModeNever, ProviderModeWellKnown:
		return nil
	default:
		return fmt.Errorf("invalid provider mode: %q", string(m))
	}
}

type GetAndPersistPlayerWithCache func(ctx context.Context, uuid string, providerMode ProviderMode) (*domain.PlayerPIT, error)

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

	return func(ctx context.Context, uuid string, providerMode ProviderMode) (*domain.PlayerPIT, error) {
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

		// Include the provider mode in the cache key so requests with different
		// modes don't serve each other's (differently-sourced) results.
		cacheKey := string(providerMode) + ":" + uuid

		player, created, err := cache.GetOrCreate(ctx, playerCache, cacheKey, func() (*domain.PlayerPIT, error) {
			switch providerMode {
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
				// Not well-known -> behave like ProviderModeNever.
				return getStoredPlayerOrFail(ctx, uuid, providerMode)
			default:
				// Unreachable: providerMode was validated above.
				return nil, fmt.Errorf("invalid provider mode: %q", providerMode)
			}
		})
		if err != nil {
			// NOTE: GetOrCreate only returns an error if create() fails.
			// The create functions handle their own error reporting.
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
		_, err := getAndPersistPlayerWithCache(ctx, uuid, ProviderModeAlways)
		if err != nil {
			// NOTE: GetAndPersistPlayerWithCache implementations handle their own error reporting
			return fmt.Errorf("failed to get updated player data: %w", err)
		}

		return nil
	}
}
