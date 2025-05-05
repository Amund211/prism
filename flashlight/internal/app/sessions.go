package app

import (
	"context"
	"errors"
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
			return nil, fmt.Errorf("UUID is not normalized")
		}

		now := nowFunc()
		if start.Before(now) && end.After(now) {
			// This is a current interval -> update the repo with the latest data
			_, err := getAndPersistPlayerWithCache(ctx, uuid)
			if err != nil && !errors.Is(err, domain.ErrPlayerNotFound) {
				logger.Error("Failed to get player data", "error", err)
				reporting.Report(ctx, err)
			}
		}

		sessions, err := repo.GetSessions(ctx, uuid, start, end)
		if err != nil {
			reporting.Report(ctx, err)
			return nil, fmt.Errorf("failed to get sessions: %w", err)
		}

		return sessions, nil
	}
}
