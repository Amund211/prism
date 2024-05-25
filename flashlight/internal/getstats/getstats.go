package getstats

import (
	"context"
	"fmt"

	"github.com/Amund211/flashlight/internal/cache"
	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/Amund211/flashlight/internal/hypixel"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/parsing"
	"github.com/Amund211/flashlight/internal/reporting"
)

func checkForHypixelError(ctx context.Context, statusCode int, playerData []byte) error {
	// Non-error status codes - check for HTML
	if statusCode <= 400 || statusCode == 404 {
		if len(playerData) > 0 && playerData[0] == '<' {
			errorMessage := "Hypixel API returned HTML"
			logging.FromContext(ctx).Error(errorMessage, "statusCode", statusCode, "data", string(playerData))
			reporting.Report(
				ctx,
				nil,
				&errorMessage,
				map[string]string{
					"statusCode": fmt.Sprint(statusCode),
					"data":       string(playerData),
				},
			)
			return fmt.Errorf("%w: %s", e.APIServerError, errorMessage)
		}

		return nil
	}

	err := fmt.Errorf("%w: Hypixel API failed (status code: %d)", e.APIServerError, statusCode)

	// Pass through certain status codes
	switch statusCode {
	case 429:
		err = fmt.Errorf("%w: Hypixel ratelimit exceeded", e.RatelimitExceededError)
	case 502:
		err = fmt.Errorf("%w: Hypixel returned 502 Bad Gateway", e.BadGateway)
	case 503:
		err = fmt.Errorf("%w: Hypixel returned 503 Service Unavailable", e.ServiceUnavailable)
	case 504:
		err = fmt.Errorf("%w: Hypixel returned 504 Gateway Timeout", e.GatewayTimeout)
	}

	logging.FromContext(ctx).Error(err.Error(), "statusCode", statusCode, "data", string(playerData))
	reporting.Report(
		ctx,
		err,
		nil,
		map[string]string{
			"statusCode": fmt.Sprint(statusCode),
			"data":       string(playerData),
		},
	)

	return err
}

func getMinifiedPlayerData(ctx context.Context, hypixelAPI hypixel.HypixelAPI, uuid string) ([]byte, int, error) {
	playerData, statusCode, err := hypixelAPI.GetPlayerData(ctx, uuid)
	if err != nil {
		reporting.Report(ctx, err, nil, nil)
		return []byte{}, -1, err
	}

	err = checkForHypixelError(ctx, statusCode, playerData)
	if err != nil {
		return []byte{}, -1, err
	}

	minifiedPlayerData, err := parsing.MinifyPlayerData(ctx, playerData)
	if err != nil {
		err = fmt.Errorf("%w: %w", e.APIServerError, err)
		reporting.Report(ctx, err, nil, map[string]string{"data": string(playerData)})
		return []byte{}, -1, err
	}

	return minifiedPlayerData, statusCode, nil
}

func GetOrCreateMinifiedPlayerData(ctx context.Context, playerCache cache.PlayerCache, hypixelAPI hypixel.HypixelAPI, uuid string) ([]byte, int, error) {
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

	minifiedPlayerData, statusCode, err := cache.GetOrCreateCachedResponse(ctx, playerCache, uuid, func() ([]byte, int, error) {
		return getMinifiedPlayerData(ctx, hypixelAPI, uuid)
	})

	if err != nil {
		return []byte{}, -1, err
	}

	logger.Info("Got minified player data", "contentLength", len(minifiedPlayerData), "statusCode", statusCode)

	return minifiedPlayerData, statusCode, nil
}
