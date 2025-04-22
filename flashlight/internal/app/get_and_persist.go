package app

import (
	"context"
	"fmt"
	"time"

	"github.com/Amund211/flashlight/internal/adapters/cache"
	"github.com/Amund211/flashlight/internal/adapters/playerprovider"
	"github.com/Amund211/flashlight/internal/adapters/playerrepository"
	"github.com/Amund211/flashlight/internal/domain"
	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
)

type GetAndPersistPlayer = func(ctx context.Context, uuid string) (*domain.PlayerPIT, error)

func getAndPersistPlayerWithoutCache(ctx context.Context, provider playerprovider.PlayerProvider, repo playerrepository.PlayerRepository, uuid string) (*domain.PlayerPIT, error) {
	player, err := provider.GetPlayer(ctx, uuid)
	if err != nil {
		return nil, err
	}

	if player != nil {
		// Ignore cancellations from the request context and try to store the data anyway
		// Take a maximum of 1 second to not block the request for too long
		storeCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 1*time.Second)
		defer cancel()
		err = repo.StorePlayer(storeCtx, player)
		if err != nil {
			err = fmt.Errorf("failed to store player: %w", err)
			reporting.Report(ctx, err)
		}
	}

	return player, nil
}

func BuildGetAndPersistPlayerWithCache(playerCache cache.Cache[*domain.PlayerPIT], provider playerprovider.PlayerProvider, repo playerrepository.PlayerRepository) GetAndPersistPlayer {
	return func(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
		logger := logging.FromContext(ctx)

		if uuid == "" {
			logger.Error("Missing uuid")
			return nil, fmt.Errorf("%w: Missing uuid", e.APIClientError)
		}
		uuidLength := len(uuid)
		if uuidLength < 10 || uuidLength > 100 {
			logger.Error("Invalid uuid", "length", uuidLength, "uuid", uuid)
			return nil, fmt.Errorf("%w: Invalid uuid", e.APIClientError)
		}

		normalizedUUID, err := strutils.NormalizeUUID(uuid)
		if err != nil {
			logger.Error("Failed to normalize uuid", "uuid", uuid, "error", err)
			return nil, fmt.Errorf("%w: Failed to normalize uuid", e.APIClientError)
		}

		player, err := cache.GetOrCreate(ctx, playerCache, normalizedUUID, func() (*domain.PlayerPIT, error) {
			return getAndPersistPlayerWithoutCache(ctx, provider, repo, normalizedUUID)
		})

		if err != nil {
			return nil, fmt.Errorf("%w: failed to cache.GetOrCreate player data: %w", e.APIServerError, err)
		}

		return player, nil
	}
}
