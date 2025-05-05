package app

import (
	"context"
	"fmt"
	"time"

	"github.com/Amund211/flashlight/internal/adapters/cache"
	"github.com/Amund211/flashlight/internal/adapters/playerprovider"
	"github.com/Amund211/flashlight/internal/adapters/playerrepository"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
)

type GetAndPersistPlayerWithCache func(ctx context.Context, uuid string) (*domain.PlayerPIT, error)

func getAndPersistPlayerWithoutCache(ctx context.Context, provider playerprovider.PlayerProvider, repo playerrepository.PlayerRepository, uuid string) (*domain.PlayerPIT, error) {
	player, err := provider.GetPlayer(ctx, uuid)
	if err != nil {
		return nil, fmt.Errorf("could not get player: %w", err)
	}

	// Ignore cancellations from the request context and try to store the data anyway
	// Take a maximum of 1 second to not block the request for too long
	storeCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 1*time.Second)
	defer cancel()
	err = repo.StorePlayer(storeCtx, player)
	if err != nil {
		err = fmt.Errorf("failed to store player: %w", err)
		reporting.Report(ctx, err)
	}

	return player, nil
}

func BuildGetAndPersistPlayerWithCache(playerCache cache.Cache[*domain.PlayerPIT], provider playerprovider.PlayerProvider, repo playerrepository.PlayerRepository) GetAndPersistPlayerWithCache {
	return func(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
		if !strutils.UUIDIsNormalized(uuid) {
			logging.FromContext(ctx).Error("UUID is not normalized", "uuid", uuid)
			err := fmt.Errorf("UUID is not normalized")
			reporting.Report(ctx, err, map[string]string{
				"uuid": uuid,
			})
			return nil, err
		}

		player, err := cache.GetOrCreate(ctx, playerCache, uuid, func() (*domain.PlayerPIT, error) {
			return getAndPersistPlayerWithoutCache(ctx, provider, repo, uuid)
		})

		if err != nil {
			return nil, fmt.Errorf("failed to cache.GetOrCreate player data: %w", err)
		}

		return player, nil
	}
}
