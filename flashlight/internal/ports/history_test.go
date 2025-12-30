package ports_test

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/domaintest"
	"github.com/Amund211/flashlight/internal/ports"
	"github.com/stretchr/testify/require"
)

func TestMakeGetHistoryHandler(t *testing.T) {
	t.Parallel()

	allowedOrigins, err := ports.NewDomainSuffixes("example.com", "test.com")
	require.NoError(t, err)

	testLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	noopMiddleware := func(h http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			h(w, r)
		}
	}

	makeGetHistory := func(t *testing.T, expectedUUID string, expectedStart, expectedEnd time.Time, expectedLimit int, history []domain.PlayerPIT, err error) (app.GetHistory, *bool) {
		called := false
		return func(ctx context.Context, uuid string, start, end time.Time, limit int) ([]domain.PlayerPIT, error) {
			t.Helper()
			require.Equal(t, expectedUUID, uuid)
			require.Equal(t, expectedStart, start)
			require.Equal(t, expectedEnd, end)
			require.Equal(t, expectedLimit, limit)

			called = true

			return history, err
		}, &called
	}

	makeGetHistoryHandler := func(getHistory app.GetHistory) http.HandlerFunc {
		return ports.MakeGetHistoryHandler(
			getHistory,
			allowedOrigins,
			testLogger,
			noopMiddleware,
		)
	}

	uuid := "01234567-89ab-cdef-0123-456789abcdef"
	start := time.Date(2023, 1, 1, 0, 0, 0, 0, time.UTC)
	startStr := "2023-01-01T00:00:00Z"
	end := time.Date(2023, 1, 31, 23, 59, 59, 999999999, time.UTC)
	endStr := "2023-01-31T23:59:59.999999999Z"
	limit := 100
	history := []domain.PlayerPIT{
		domaintest.NewPlayerBuilder(uuid, start).
			WithExperience(500).
			WithOverallStats(
				domaintest.NewStatsBuilder().WithFinalKills(10).Build(),
			).Build(),
	}
	historyJSON, err := ports.HistoryToRainbowHistoryData(history)
	require.NoError(t, err)

	makeRequest := func(
		uuid string,
		startStr, endStr string,
		limit int,
	) *http.Request {
		body := io.NopCloser(
			strings.NewReader(
				fmt.Sprintf(
					`{"uuid":"%s","start":"%s","end":"%s","limit":%d}`,
					uuid,
					startStr,
					endStr,
					limit,
				),
			),
		)
		return httptest.NewRequest("GET", "/history", body)

	}

	t.Run("successful history retrieval", func(t *testing.T) {
		t.Parallel()

		getHistoryFunc, called := makeGetHistory(t, uuid, start, end, limit, history, nil)
		handler := makeGetHistoryHandler(getHistoryFunc)

		req := makeRequest(uuid, startStr, endStr, limit)
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusOK, w.Code)
		require.NoError(t, err)
		require.JSONEq(t, string(historyJSON), w.Body.String())
		require.True(t, *called)
	})

	t.Run("start time == end time", func(t *testing.T) {
		t.Parallel()

		start := time.Date(2023, 1, 1, 0, 0, 0, 0, time.UTC)
		startStr := "2023-01-01T00:00:00Z"
		end := time.Date(2023, 1, 1, 0, 0, 0, 0, time.UTC)
		endStr := "2023-01-01T00:00:00Z"

		getHistoryFunc, called := makeGetHistory(t, uuid, start, end, limit, history, nil)
		handler := makeGetHistoryHandler(getHistoryFunc)

		req := makeRequest(uuid, startStr, endStr, limit)
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusOK, w.Code)
		require.NoError(t, err)
		require.JSONEq(t, string(historyJSON), w.Body.String())
		require.True(t, *called)
	})

	t.Run("invalid UUID format", func(t *testing.T) {
		t.Parallel()

		getHistoryFunc, called := makeGetHistory(t, uuid, start, end, limit, history, nil)
		handler := makeGetHistoryHandler(getHistoryFunc)

		req := makeRequest("invalid-uuid", startStr, endStr, limit)
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusBadRequest, w.Code)
		require.Contains(t, w.Body.String(), "invalid uuid")
		require.False(t, *called)
	})

	t.Run("start time after end time", func(t *testing.T) {
		t.Parallel()

		getHistoryFunc, called := makeGetHistory(t, uuid, start, end, limit, history, nil)
		handler := makeGetHistoryHandler(getHistoryFunc)

		req := makeRequest(uuid, "2023-01-01T00:00:00.000000001Z", "2023-01-01T00:00:00.000000000Z", limit)
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusBadRequest, w.Code)
		require.Contains(t, w.Body.String(), "Start time cannot be after end time")
		require.False(t, *called)
	})

	t.Run("invalid limits", func(t *testing.T) {
		t.Parallel()
		for _, invalidLimit := range []int{-1, 0, 1, 1001} {
			t.Run(fmt.Sprintf("limit=%d", invalidLimit), func(t *testing.T) {
				t.Parallel()

				getHistoryFunc, called := makeGetHistory(t, uuid, start, end, invalidLimit, history, nil)
				handler := makeGetHistoryHandler(getHistoryFunc)

				req := makeRequest(uuid, startStr, endStr, invalidLimit)
				w := httptest.NewRecorder()

				handler.ServeHTTP(w, req)

				require.Equal(t, http.StatusBadRequest, w.Code)
				require.Contains(t, w.Body.String(), "invalid limit")
				require.False(t, *called)
			})
		}
	})
}
