package processing

import (
	"context"
	"fmt"

	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/reporting"
)

func checkForHypixelError(ctx context.Context, statusCode int, playerData []byte) error {
	// Non-error status codes - check for HTML
	if statusCode <= 400 || statusCode == 404 {
		if len(playerData) > 0 && playerData[0] == '<' {
			return fmt.Errorf("%w: Hypixel API returned HTML %w", e.APIServerError, e.RetriableError)
		}

		return nil
	}

	// Error for unknown status code
	err := fmt.Errorf("%w: Hypixel API returned unsupported status code: %d", e.APIServerError, statusCode)

	// Errors for known status codes
	switch statusCode {
	case 429:
		err = fmt.Errorf("%w: Hypixel ratelimit exceeded %w", e.RatelimitExceededError, e.RetriableError)
	case 500, 502, 503, 504:
		err = fmt.Errorf("%w: Hypixel returned status code %d %w", e.APIServerError, statusCode, e.RetriableError)
	}

	return err
}

func ProcessPlayerData(ctx context.Context, playerData []byte, statusCode int) ([]byte, int, error) {
	err := checkForHypixelError(ctx, statusCode, playerData)
	if err != nil {
		reporting.Report(
			ctx,
			err,
			map[string]string{
				"statusCode": fmt.Sprint(statusCode),
				"data":       string(playerData),
			},
		)
		logging.FromContext(ctx).Error(
			"Got response from hypixel",
			"status", "error",
			"error", err.Error(),
			"data", string(playerData),
			"statusCode", statusCode,
			"contentLength", len(playerData),
		)
		return []byte{}, -1, err
	}

	logging.FromContext(ctx).Error(
		"Got response from hypixel",
		"status", "success",
		"statusCode", statusCode,
		"contentLength", len(playerData),
	)

	parsedPlayerData, err := ParsePlayerData(ctx, playerData)
	if err != nil {
		err = fmt.Errorf("%w: failed to parse player data: %w", e.APIServerError, err)
		reporting.Report(
			ctx,
			err,
			map[string]string{
				"statusCode": fmt.Sprint(statusCode),
				"data":       string(playerData),
			},
		)
		return []byte{}, -1, err
	}

	processedStatusCode := 200
	if parsedPlayerData.Success && parsedPlayerData.Player == nil {
		processedStatusCode = 404
	}

	minifiedPlayerData, err := MarshalPlayerData(ctx, parsedPlayerData)
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
