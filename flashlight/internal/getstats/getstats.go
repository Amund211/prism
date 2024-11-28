package getstats

import (
	"context"
	"fmt"
	"time"

	"github.com/Amund211/flashlight/internal/cache"
	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/Amund211/flashlight/internal/hypixel"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/processing"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/storage"
)

func getAndProcessPlayerData(ctx context.Context, hypixelAPI hypixel.HypixelAPI, persistor storage.StatsPersistor, uuid string) ([]byte, int, error) {
	playerData, statusCode, err := hypixelAPI.GetPlayerData(ctx, uuid)
	if err != nil {
		reporting.Report(ctx, err)
		return []byte{}, -1, err
	}
	queriedAt := time.Now()

	parsedAPIResponse, processedStatusCode, err := processing.ParseHypixelAPIResponse(ctx, playerData, statusCode)
	if err != nil {
		return []byte{}, -1, err
	}

	if parsedAPIResponse.Player != nil {
		err = persistor.StoreStats(ctx, uuid, playerData, queriedAt)
		if err != nil {
			err = fmt.Errorf("failed to persist player data: %w", err)
			reporting.Report(
				ctx,
				err,
				map[string]string{
					"processedStatusCode": fmt.Sprint(processedStatusCode),
					"statusCode":          fmt.Sprint(statusCode),
					"data":                string(playerData),
				},
			)
		}
	}

	minifiedPlayerData, err := processing.MarshalPlayerData(ctx, parsedAPIResponse)
	if err != nil {
		err = fmt.Errorf("%w: failed to marshal player data: %w", e.APIServerError, err)
		reporting.Report(
			ctx,
			err,
			map[string]string{
				"processedStatusCode": fmt.Sprint(processedStatusCode),
				"statusCode":          fmt.Sprint(statusCode),
				"data":                string(playerData),
			},
		)
		return []byte{}, -1, err
	}

	return minifiedPlayerData, processedStatusCode, nil
}

func GetOrCreateProcessedPlayerData(ctx context.Context, playerCache cache.PlayerCache, hypixelAPI hypixel.HypixelAPI, persistor storage.StatsPersistor, uuid string) ([]byte, int, error) {
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

	processedPlayerData, statusCode, err := cache.GetOrCreateCachedResponse(ctx, playerCache, uuid, func() ([]byte, int, error) {
		return getAndProcessPlayerData(ctx, hypixelAPI, persistor, uuid)
	})

	if err != nil {
		return []byte{}, -1, err
	}

	logger.Info("Got minified player data", "contentLength", len(processedPlayerData), "statusCode", statusCode)

	return processedPlayerData, statusCode, nil
}
