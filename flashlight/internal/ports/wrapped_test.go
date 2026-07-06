package ports_test

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/domaintest"
	"github.com/Amund211/flashlight/internal/ports"
)

func TestMakeGetWrappedHandler(t *testing.T) {
	t.Parallel()

	allowedOrigins, err := ports.NewDomainSuffixes("example.com", "test.com")
	require.NoError(t, err)

	testLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	noopMiddleware := func(h http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			h(w, r)
		}
	}

	makeGetPlayerPITs := func(t *testing.T, expectedUUID string, playerPITs []domain.PlayerPIT, err error) (app.GetPlayerPITs, *bool) {
		called := false
		return func(ctx context.Context, uuid string, start, end time.Time) ([]domain.PlayerPIT, error) {
			t.Helper()
			require.Equal(t, expectedUUID, uuid)

			called = true

			return playerPITs, err
		}, &called
	}

	makeGetWrappedHandler := func(getPlayerPITs app.GetPlayerPITs) http.HandlerFunc {
		stubRegisterUserVisit := func(ctx context.Context, userID string, ipHash string, userAgent string) (domain.User, error) {
			return domain.User{}, nil
		}
		return ports.MakeGetWrappedHandler(
			getPlayerPITs,
			app.BuildComputeSessions(time.Now),
			stubRegisterUserVisit,
			allowedOrigins,
			testLogger,
			noopMiddleware,
			emptyBlocklistConfig,
		)
	}

	uuid := "01234567-89ab-cdef-0123-456789abcdef"

	makeRequest := func(uuid string, year string) *http.Request {
		req := httptest.NewRequestWithContext(t.Context(), "GET", "/wrapped/"+uuid+"/"+year, nil)
		req.SetPathValue("uuid", uuid)
		req.SetPathValue("year", year)
		return req
	}

	t.Run("successful wrapped retrieval", func(t *testing.T) {
		t.Parallel()

		playerPITs := []domain.PlayerPIT{}
		getPlayerPITsFunc, called := makeGetPlayerPITs(t, uuid, playerPITs, nil)
		handler := makeGetWrappedHandler(getPlayerPITsFunc)

		req := makeRequest(uuid, "2023")
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusOK, w.Code)
		require.True(t, *called)

		var response map[string]interface{}
		err := json.Unmarshal(w.Body.Bytes(), &response)
		require.NoError(t, err)

		require.Equal(t, true, response["success"])
		require.Equal(t, uuid, response["uuid"])
		require.Equal(t, float64(2023), response["year"])
	})

	t.Run("4v4 win and final kill streaks", func(t *testing.T) {
		t.Parallel()

		base := time.Date(2023, time.June, 1, 12, 0, 0, 0, time.UTC)
		pb := domaintest.NewPlayerBuilder(uuid).FromDB().Fourv4()
		playerPITs := []domain.PlayerPIT{
			pb.Build(base),
			pb.WithGamesPlayed(2).WithWins(2).WithFinalKills(3).Build(base.Add(20 * time.Minute)),
			pb.WithGamesPlayed(3).WithWins(3).WithFinalKills(5).Build(base.Add(40 * time.Minute)),
			pb.WithGamesPlayed(4).WithLosses(1).WithFinalDeaths(1).Build(base.Add(60 * time.Minute)),
		}
		getPlayerPITsFunc, called := makeGetPlayerPITs(t, uuid, playerPITs, nil)
		handler := makeGetWrappedHandler(getPlayerPITsFunc)

		req := makeRequest(uuid, "2023")
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusOK, w.Code)
		require.True(t, *called)

		var response map[string]interface{}
		err := json.Unmarshal(w.Body.Bytes(), &response)
		require.NoError(t, err)

		require.Equal(t, true, response["success"])

		sessionStats, ok := response["sessionStats"].(map[string]interface{})
		require.True(t, ok)

		winstreaks, ok := sessionStats["winstreaks"].(map[string]interface{})
		require.True(t, ok)
		fourv4Winstreak, ok := winstreaks["4v4"].(map[string]interface{})
		require.True(t, ok)
		require.Equal(t, float64(3), fourv4Winstreak["highest"])
		require.Equal(t, "2023-06-01T12:40:00Z", fourv4Winstreak["when"])

		finalKillStreaks, ok := sessionStats["finalKillStreaks"].(map[string]interface{})
		require.True(t, ok)
		fourv4FKStreak, ok := finalKillStreaks["4v4"].(map[string]interface{})
		require.True(t, ok)
		require.Equal(t, float64(5), fourv4FKStreak["highest"])
		require.Equal(t, "2023-06-01T12:40:00Z", fourv4FKStreak["when"])
	})

	t.Run("empty sessions", func(t *testing.T) {
		t.Parallel()

		getPlayerPITsFunc, called := makeGetPlayerPITs(t, uuid, []domain.PlayerPIT{}, nil)
		handler := makeGetWrappedHandler(getPlayerPITsFunc)

		req := makeRequest(uuid, "2023")
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusOK, w.Code)
		require.True(t, *called)

		var response map[string]interface{}
		err := json.Unmarshal(w.Body.Bytes(), &response)
		require.NoError(t, err)

		require.Equal(t, true, response["success"])
	})

	t.Run("invalid UUID format", func(t *testing.T) {
		t.Parallel()

		getPlayerPITsFunc, called := makeGetPlayerPITs(t, uuid, []domain.PlayerPIT{}, nil)
		handler := makeGetWrappedHandler(getPlayerPITsFunc)

		req := makeRequest("invalid-uuid", "2023")
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusBadRequest, w.Code)
		require.False(t, *called)

		var response map[string]interface{}
		err := json.Unmarshal(w.Body.Bytes(), &response)
		require.NoError(t, err)

		require.Equal(t, false, response["success"])
		require.Equal(t, "invalid uuid", response["cause"])
	})

	t.Run("invalid year format", func(t *testing.T) {
		t.Parallel()

		getPlayerPITsFunc, called := makeGetPlayerPITs(t, uuid, []domain.PlayerPIT{}, nil)
		handler := makeGetWrappedHandler(getPlayerPITsFunc)

		req := makeRequest(uuid, "not-a-year")
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusBadRequest, w.Code)
		require.False(t, *called)

		var response map[string]interface{}
		err := json.Unmarshal(w.Body.Bytes(), &response)
		require.NoError(t, err)

		require.Equal(t, false, response["success"])
		require.Equal(t, "invalid year", response["cause"])
	})

	t.Run("year out of range", func(t *testing.T) {
		t.Parallel()

		getPlayerPITsFunc, called := makeGetPlayerPITs(t, uuid, []domain.PlayerPIT{}, nil)
		handler := makeGetWrappedHandler(getPlayerPITsFunc)

		req := makeRequest(uuid, "1999")
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusBadRequest, w.Code)
		require.False(t, *called)

		var response map[string]interface{}
		err := json.Unmarshal(w.Body.Bytes(), &response)
		require.NoError(t, err)

		require.Equal(t, false, response["success"])
		require.Equal(t, "invalid year", response["cause"])
	})
}
