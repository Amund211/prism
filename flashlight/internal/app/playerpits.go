package app

import (
	"context"
	"fmt"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
)

type playerPITsPlayerRepository interface {
	GetPlayerPITs(ctx context.Context, playerUUID string, start, end time.Time) ([]domain.PlayerPIT, error)
}

type GetPlayerPITs = func(
	ctx context.Context,
	uuid string,
	start, end time.Time,
) ([]domain.PlayerPIT, error)

func BuildGetPlayerPITs(
	repo playerPITsPlayerRepository,
	updatePlayerInInterval UpdatePlayerInInterval,
) GetPlayerPITs {
	return func(ctx context.Context,
		uuid string,
		start, end time.Time,
	) ([]domain.PlayerPIT, error) {
		if !strutils.UUIDIsNormalized(uuid) {
			err := fmt.Errorf("UUID is not normalized")
			reporting.Report(ctx, err)
			return nil, err
		}

		if start.After(end) {
			err := fmt.Errorf("start time is after end time")
			reporting.Report(ctx, err)
			return nil, err
		}

		err := updatePlayerInInterval(ctx, uuid, start, end)
		if err != nil {
			// NOTE: UpdatePlayerInInterval implementations handle their own error reporting
			logging.FromContext(ctx).ErrorContext(ctx, "Failed to update player data in interval", "error", err)

			// NOTE: We continue even though we failed to update player data
			// We may still be able to get the data and fulfill the request
		}

		playerPITs, err := repo.GetPlayerPITs(ctx, uuid, start, end)
		if err != nil {
			// NOTE: PlayerRepository implementations handle their own error reporting
			return nil, fmt.Errorf("failed to get playerpits: %w", err)
		}

		return playerPITs, nil
	}
}
