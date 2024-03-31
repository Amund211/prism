package getstats

import (
	"context"
	"fmt"
	"log"

	"github.com/Amund211/flashlight/internal/cache"
	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/Amund211/flashlight/internal/hypixel"
	"github.com/Amund211/flashlight/internal/parsing"
	"github.com/Amund211/flashlight/internal/reporting"
)

func getMinifiedPlayerData(ctx context.Context, hypixelAPI hypixel.HypixelAPI, uuid string) ([]byte, int, error) {
	playerData, statusCode, err := hypixelAPI.GetPlayerData(uuid)
	if err != nil {
		return []byte{}, -1, err
	}

	if len(playerData) > 0 && playerData[0] == '<' {
		log.Println("Hypixel returned HTML")
		return []byte{}, -1, fmt.Errorf("%w: Hypixel returned HTML", e.APIServerError)
	}

	if statusCode >= 400 && statusCode != 404 {
		errorMessage := "Hypixel API returned status code >= 400, != 404"
		reporting.Report(
			ctx,
			nil,
			&errorMessage,
			map[string]string{
				"statusCode": fmt.Sprint(statusCode),
				"data":       string(playerData),
			},
		)
		return []byte{}, -1, fmt.Errorf("%w: Hypixel API failed", e.APIServerError)
	}

	minifiedPlayerData, err := parsing.MinifyPlayerData(playerData)
	if err != nil {
		return []byte{}, -1, fmt.Errorf("%w: %w", e.APIServerError, err)
	}

	return minifiedPlayerData, statusCode, nil
}

func GetOrCreateMinifiedPlayerData(ctx context.Context, playerCache cache.PlayerCache, hypixelAPI hypixel.HypixelAPI, uuid string) ([]byte, int, error) {
	if uuid == "" {
		return []byte{}, -1, fmt.Errorf("%w: Missing uuid", e.APIClientError)
	}
	uuidLength := len(uuid)
	if uuidLength < 10 || uuidLength > 100 {
		return []byte{}, -1, fmt.Errorf("%w: Invalid uuid (length=%d)", e.APIClientError, uuidLength)
	}

	minifiedPlayerData, statusCode, err := cache.GetOrCreateCachedResponse(playerCache, uuid, func() ([]byte, int, error) {
		return getMinifiedPlayerData(ctx, hypixelAPI, uuid)
	})

	if err != nil {
		return []byte{}, -1, err
	}

	return minifiedPlayerData, statusCode, nil
}
