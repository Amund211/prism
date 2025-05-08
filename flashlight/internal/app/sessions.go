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
	getAndPersistPlayerWithCache GetAndPersistPlayerWithCache,
	nowFunc func() time.Time,
) GetSessions {
	return func(ctx context.Context,
		uuid string,
		start, end time.Time,
	) ([]domain.Session, error) {
		logger := logging.FromContext(ctx)

		if !strutils.UUIDIsNormalized(uuid) {
			err := fmt.Errorf("UUID is not normalized")
			reporting.Report(ctx, err, map[string]string{
				"uuid":  uuid,
				"start": end.Format(time.RFC3339),
				"end":   end.Format(time.RFC3339),
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

		sessions, err := repo.GetSessions(ctx, uuid, start, end)
		if err != nil {
			// NOTE: PlayerRepository implementations handle their own error reporting
			return nil, fmt.Errorf("failed to get sessions: %w", err)
		}

		return sessions, nil
	}
}
