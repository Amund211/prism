package playerprovider

import (
	"context"
	"fmt"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
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
	if !strutils.UUIDIsNormalized(uuid) {
		logging.FromContext(ctx).Error("UUID is not normalized", "uuid", uuid)
		err := fmt.Errorf("UUID is not normalized")
		reporting.Report(ctx, err, map[string]string{
			"uuid": uuid,
		})
		return nil, err
	}

	playerData, statusCode, queriedAt, err := h.hypixelAPI.GetPlayerData(ctx, uuid)
	if err != nil {
		reporting.Report(ctx, fmt.Errorf("failed to get player data: %w", err), map[string]string{
			"uuid": uuid,
		})
		return nil, fmt.Errorf("failed to get player data: %w", err)
	}

	player, err := HypixelAPIResponseToPlayerPIT(ctx, uuid, queriedAt, playerData, statusCode)
	if err != nil {
		reporting.Report(ctx, fmt.Errorf("failed to convert hypixel api response to player: %w", err), map[string]string{
			"uuid":       uuid,
			"data":       string(playerData),
			"statusCode": fmt.Sprint(statusCode),
		})
		return nil, fmt.Errorf("failed to convert hypixel api response to player: %w", err)
	}

	return player, nil
}
