package app

import (
	"context"
	"fmt"
	"time"

	"github.com/Amund211/flashlight/internal/adapters/playerrepository"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
)

type GetHistory = func(
	ctx context.Context,
	uuid string,
	start, end time.Time,
	limit int,
) ([]domain.PlayerPIT, error)

func BuildGetHistory(
	repo playerrepository.PlayerRepository,
	updatePlayerInInterval UpdatePlayerInInterval,
) GetHistory {
	return func(ctx context.Context,
		uuid string,
		start, end time.Time,
		limit int,
	) ([]domain.PlayerPIT, error) {
		logger := logging.FromContext(ctx)

		if !strutils.UUIDIsNormalized(uuid) {
			err := fmt.Errorf("UUID is not normalized")
			reporting.Report(ctx, err)
			return nil, err
		}

		err := updatePlayerInInterval(ctx, uuid, start, end)
		if err != nil {
			// NOTE: UpdatePlayerInInterval implementations handle their own error reporting
			logger.Error("Failed to update player data in interval", "error", err)

			// NOTE: We continue even though we failed to update player data
			// We may still be able to get the history and fulfill the request
		}

		history, err := repo.GetHistory(ctx, uuid, start, end, limit)
		if err != nil {
			// NOTE: PlayerRepository implementations handle their own error reporting
			return nil, fmt.Errorf("failed to get history: %w", err)
		}

		return history, nil
	}
}
