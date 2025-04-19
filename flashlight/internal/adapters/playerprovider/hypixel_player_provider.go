package playerprovider

import (
	"context"
	"fmt"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
)

type hypixelPlayerProvider struct {
	hypixelAPI HypixelAPI
}

func NewHypixelPlayerProvider(hypixelAPI HypixelAPI) PlayerProvider {
	return &hypixelPlayerProvider{
		hypixelAPI: hypixelAPI,
	}
}

func (h *hypixelPlayerProvider) GetPlayer(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
	normalizedUUID, err := strutils.NormalizeUUID(uuid)
	if err != nil {
		reporting.Report(ctx, fmt.Errorf("failed to normalize uuid: %w", err), map[string]string{
			"uuid": uuid,
		})
		return nil, fmt.Errorf("failed to normalize uuid: %w", err)
	}

	playerData, statusCode, queriedAt, err := h.hypixelAPI.GetPlayerData(ctx, normalizedUUID)
	if err != nil {
		reporting.Report(ctx, fmt.Errorf("failed to get player data: %w", err), map[string]string{
			"uuid": normalizedUUID,
		})
		return nil, fmt.Errorf("failed to get player data: %w", err)
	}

	player, err := HypixelAPIResponseToPlayerPIT(ctx, normalizedUUID, queriedAt, playerData, statusCode)
	if err != nil {
		reporting.Report(ctx, fmt.Errorf("failed to convert hypixel api response to player: %w", err), map[string]string{
			"uuid":       normalizedUUID,
			"data":       string(playerData),
			"statusCode": fmt.Sprint(statusCode),
		})
		return nil, fmt.Errorf("failed to convert hypixel api response to player: %w", err)
	}

	return player, nil
}
