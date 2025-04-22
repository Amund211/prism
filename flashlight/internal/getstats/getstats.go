package getstats

import (
	"context"
	"fmt"
	"time"

	"github.com/Amund211/flashlight/internal/adapters/cache"
	"github.com/Amund211/flashlight/internal/adapters/playerprovider"
	"github.com/Amund211/flashlight/internal/adapters/playerrepository"
	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
)

func getAndProcessPlayerData(ctx context.Context, provider playerprovider.PlayerProvider, repo playerrepository.PlayerRepository, uuid string) ([]byte, int, error) {
	player, err := provider.GetPlayer(ctx, uuid)
	if err != nil {
		return []byte{}, -1, err
	}

	apiResponseFromDomain := playerprovider.DomainPlayerToHypixelAPIResponse(player)

	minifiedPlayerData, err := playerprovider.MarshalPlayerData(ctx, apiResponseFromDomain)
	if err != nil {
		err = fmt.Errorf("%w: failed to marshal player data: %w", e.APIServerError, err)
		reporting.Report(ctx, err)
		return []byte{}, -1, err
	}

	if apiResponseFromDomain.Player != nil {
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

	return minifiedPlayerData, 200, nil
}

func GetOrCreateProcessedPlayerData(ctx context.Context, playerCache cache.PlayerCache, provider playerprovider.PlayerProvider, repo playerrepository.PlayerRepository, uuid string) ([]byte, int, error) {
	logger := logging.FromContext(ctx)

	if uuid == "" {
		logger.Error("Missing uuid")
		return []byte{}, -1, fmt.Errorf("%w: Missing uuid", e.APIClientError)
	}
	uuidLength := len(uuid)
	if uuidLength < 10 || uuidLength > 100 {
		logger.Error("Invalid uuid", "length", uuidLength, "uuid", uuid)
		return []byte{}, -1, fmt.Errorf("%w: Invalid uuid", e.APIClientError)
	}

	normalizedUUID, err := strutils.NormalizeUUID(uuid)
	if err != nil {
		logger.Error("Failed to normalize uuid", "uuid", uuid, "error", err)
		return []byte{}, -1, fmt.Errorf("%w: Failed to normalize uuid", e.APIClientError)
	}

	processedPlayerData, statusCode, err := cache.GetOrCreateCachedResponse(ctx, playerCache, normalizedUUID, func() ([]byte, int, error) {
		return getAndProcessPlayerData(ctx, provider, repo, normalizedUUID)
	})

	if err != nil {
		return []byte{}, -1, err
	}

	logger.Info("Got minified player data", "contentLength", len(processedPlayerData), "statusCode", statusCode)

	return processedPlayerData, statusCode, nil
}
