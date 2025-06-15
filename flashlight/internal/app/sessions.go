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

type GetSessions = func(
	ctx context.Context,
	uuid string,
	start, end time.Time,
) ([]domain.Session, error)

func BuildGetSessions(
	repo playerrepository.PlayerRepository,
	updatePlayerInInterval UpdatePlayerInInterval,
) GetSessions {
	return func(ctx context.Context,
		uuid string,
		start, end time.Time,
	) ([]domain.Session, error) {
		logger := logging.FromContext(ctx)

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
			logger.Error("Failed to update player data in interval", "error", err)

			// NOTE: We continue even though we failed to update player data
			// We may still be able to get the history and fulfill the request
		}

		sessions, err := repo.GetSessions(ctx, uuid, start, end)
		if err != nil {
			// NOTE: PlayerRepository implementations handle their own error reporting
			return nil, fmt.Errorf("failed to get sessions: %w", err)
		}

		return sessions, nil
	}
}
