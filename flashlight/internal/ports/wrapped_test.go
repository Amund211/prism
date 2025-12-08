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

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/ports"
	"github.com/stretchr/testify/require"
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
		return ports.MakeGetWrappedHandler(
			getPlayerPITs,
			allowedOrigins,
			testLogger,
			noopMiddleware,
		)
	}

	uuid := "01234567-89ab-cdef-0123-456789abcdef"

	makeRequest := func(uuid string, year string) *http.Request {
		req := httptest.NewRequest("GET", "/wrapped/"+uuid+"/"+year, nil)
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
