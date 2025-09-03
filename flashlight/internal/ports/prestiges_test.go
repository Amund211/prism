package ports_test

import (
	"context"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/ports"
	"github.com/stretchr/testify/require"
)

func TestGetPrestigesHandler(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(os.Stderr, nil))
	sentryMiddleware := func(next http.HandlerFunc) http.HandlerFunc { return next }
	allowedOrigins, err := ports.NewDomainSuffixes("example.com", "test.com")
	require.NoError(t, err)

	makeFindMilestoneAchievements := func(expectedUUID string, achievements []domain.MilestoneAchievement, err error) app.FindMilestoneAchievements {
		return func(ctx context.Context, playerUUID string, gamemode domain.Gamemode, stat domain.Stat, milestones []int64) ([]domain.MilestoneAchievement, error) {
			require.Equal(t, domain.GamemodeOverall, gamemode)
			require.Equal(t, domain.StatStars, stat)

			require.Len(t, milestones, 100)
			for i, milestone := range milestones {
				expected := int64((i + 1) * 100)
				require.Equal(t, expected, milestone)
			}

			return achievements, err
		}
	}

	makeAssertNotCalled := func(t *testing.T) app.FindMilestoneAchievements {
		return func(ctx context.Context, playerUUID string, gamemode domain.Gamemode, stat domain.Stat, milestones []int64) ([]domain.MilestoneAchievement, error) {
			t.Helper()
			require.False(t, true, "FindMilestoneAchievements should not have been called")
			return nil, nil
		}
	}

	makeRequest := func(uuid string) *http.Request {
		req := httptest.NewRequest("GET", "/v1/prestiges/"+uuid, nil)
		req.SetPathValue("uuid", uuid)
		return req
	}

	t.Run("Successful request", func(t *testing.T) {
		playerUUID := "550e8400-e29b-41d4-a716-446655440000"

		findMilestoneAchievements := makeFindMilestoneAchievements(
			playerUUID,
			[]domain.MilestoneAchievement{
				{
					Milestone: 100,
					After: &domain.MilestoneAchievementStats{
						Player: domain.PlayerPIT{
							UUID:       playerUUID,
							QueriedAt:  time.Date(2021, 1, 1, 12, 0, 0, 0, time.UTC),
							Experience: 48_700, // Exactly 100 stars
						},
						Value: 100,
					},
				},
			},
			nil,
		)

		handler := ports.MakeGetPrestigesHandler(findMilestoneAchievements, allowedOrigins, logger, sentryMiddleware)

		req := makeRequest(playerUUID)
		w := httptest.NewRecorder()

		handler(w, req)

		require.Equal(t, http.StatusOK, w.Code)
		require.Equal(t, "application/json", w.Header().Get("Content-Type"))

		require.JSONEq(t, `
		{
			"success": true,
			"prestiges": [
				{
					"stars": 100,
					"first_seen": {
						"experience": 48700,
						"queried_at": "2021-01-01T12:00:00Z",
						"stars": 100
					}
				}
			]
		}`, w.Body.String())
	})

	t.Run("Invalid UUID", func(t *testing.T) {
		handler := ports.MakeGetPrestigesHandler(makeAssertNotCalled(t), allowedOrigins, logger, sentryMiddleware)

		req := makeRequest("invalid-uuid")
		w := httptest.NewRecorder()

		handler(w, req)

		require.Equal(t, http.StatusBadRequest, w.Code)
		require.Equal(t, "application/json", w.Header().Get("Content-Type"))
		require.Contains(t, w.Body.String(), "Invalid UUID")
	})

	t.Run("Missing UUID", func(t *testing.T) {
		handler := ports.MakeGetPrestigesHandler(makeAssertNotCalled(t), allowedOrigins, logger, sentryMiddleware)

		req := httptest.NewRequest("GET", "/v1/prestiges", nil)
		w := httptest.NewRecorder()

		handler(w, req)

		require.Equal(t, http.StatusBadRequest, w.Code)
		require.Equal(t, "application/json", w.Header().Get("Content-Type"))
		require.Contains(t, w.Body.String(), "Invalid UUID")
	})
}
