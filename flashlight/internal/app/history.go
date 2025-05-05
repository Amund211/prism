package app

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/Amund211/flashlight/internal/adapters/playerrepository"
	"github.com/Amund211/flashlight/internal/domain"
	e "github.com/Amund211/flashlight/internal/errors"
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
			return nil, fmt.Errorf("%w: UUID is not normalized", e.APIServerError)
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

		history, err := repo.GetHistory(ctx, uuid, start, end, limit)
		if err != nil {
			reporting.Report(ctx, err)
			return nil, fmt.Errorf("failed to get history: %w", err)
		}

		return history, nil
	}
}
