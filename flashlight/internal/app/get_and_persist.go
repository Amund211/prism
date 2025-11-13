package app

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/Amund211/flashlight/internal/adapters/cache"
	"github.com/Amund211/flashlight/internal/adapters/playerprovider"
	"github.com/Amund211/flashlight/internal/adapters/playerrepository"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
)

type GetAndPersistPlayerWithCache func(ctx context.Context, uuid string) (*domain.PlayerPIT, error)

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
			),
		)
	}

	return func(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
		if !strutils.UUIDIsNormalized(uuid) {
			logging.FromContext(ctx).ErrorContext(ctx, "UUID is not normalized", "uuid", uuid)
			err := fmt.Errorf("UUID is not normalized")
			reporting.Report(ctx, err)
			track(ctx, trackingInfo{success: false, invalidInput: true})
			return nil, err
		}

		player, created, err := cache.GetOrCreate(ctx, playerCache, uuid, func() (*domain.PlayerPIT, error) {
			return getAndPersistPlayerWithoutCache(ctx, provider, repo, uuid)
		})
		if err != nil {
			// NOTE: GetOrCreate only returns an error if create() fails.
			// getAndPersistPlayerWithoutCache handles its own error reporting
			if errors.Is(err, domain.ErrPlayerNotFound) {
				track(ctx, trackingInfo{success: true, found: false})
			} else {
				track(ctx, trackingInfo{success: false})
			}
			return nil, fmt.Errorf("failed to cache.GetOrCreate player data: %w", err)
		}

		track(ctx, trackingInfo{success: true, found: true, cached: !created})
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
		_, err := getAndPersistPlayerWithCache(ctx, uuid)
		if err != nil {
			// NOTE: GetAndPersistPlayerWithCache implementations handle their own error reporting
			return fmt.Errorf("failed to get updated player data: %w", err)
		}

		return nil
	}
}
