package app

import (
	"context"
	"fmt"
	"strconv"
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
	getAndPersistPlayerWithCache GetAndPersistPlayerWithCache,
	nowFunc func() time.Time,
) GetHistory {
	return func(ctx context.Context,
		uuid string,
		start, end time.Time,
		limit int,
	) ([]domain.PlayerPIT, error) {
		logger := logging.FromContext(ctx)

		if !strutils.UUIDIsNormalized(uuid) {
			err := fmt.Errorf("UUID is not normalized")
			reporting.Report(ctx, err, map[string]string{
				"uuid":  uuid,
				"start": start.Format(time.RFC3339),
				"end":   end.Format(time.RFC3339),
				"limit": strconv.Itoa(limit),
			})
			return nil, err
		}

		now := nowFunc()
		if start.Before(now) && end.After(now) {
			// This is a current interval -> update the repo with the latest data
			_, err := getAndPersistPlayerWithCache(ctx, uuid)
			if err != nil {
				// NOTE: GetAndPersistPlayerWithCache implementations handle their own error reporting
				logger.Error("Failed to get updated player data", "error", err)

				// NOTE: We continue even though we failed to get updated player data
				// We may still be able to get the history and fulfill the request
			}
		}

		history, err := repo.GetHistory(ctx, uuid, start, end, limit)
		if err != nil {
			// NOTE: PlayerRepository implementations handle their own error reporting
			return nil, fmt.Errorf("failed to get history: %w", err)
		}

		return history, nil
	}
}
