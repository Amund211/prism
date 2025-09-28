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

func TestMakeGetSessionsHandler(t *testing.T) {
	t.Parallel()

	allowedOrigins, err := ports.NewDomainSuffixes("example.com", "test.com")
	require.NoError(t, err)

	testLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	noopMiddleware := func(h http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			h(w, r)
		}
	}

	makeGetSessions := func(t *testing.T, expectedUUID string, expectedStart, expectedEnd time.Time, sessions []domain.Session, err error) (app.GetSessions, *bool) {
		called := false
		return func(ctx context.Context, uuid string, start, end time.Time) ([]domain.Session, error) {
			t.Helper()
			require.Equal(t, expectedUUID, uuid)
			require.Equal(t, expectedStart, start)
			require.Equal(t, expectedEnd, end)

			called = true

			return sessions, err
		}, &called
	}

	makeGetSessionsHandler := func(getSessions app.GetSessions) http.HandlerFunc {
		return ports.MakeGetSessionsHandler(
			getSessions,
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
	sessions := []domain.Session{
		{
			Start: domaintest.NewPlayerBuilder(uuid, start).
				WithExperience(500).
				WithOverallStats(
					domaintest.NewStatsBuilder().WithFinalKills(10).Build(),
				).Build(),
			End: domaintest.NewPlayerBuilder(uuid, end).
				WithExperience(1000).
				WithOverallStats(
					domaintest.NewStatsBuilder().WithFinalKills(11).Build(),
				).Build(),
			Consecutive: true,
		},
	}
	sessionsJSON, err := ports.SessionsToRainbowSessionsData(sessions)
	require.NoError(t, err)

	makeRequest := func(
		uuid string,
		startStr, endStr string,
	) *http.Request {
		body := io.NopCloser(
			strings.NewReader(
				fmt.Sprintf(
					`{"uuid":"%s","start":"%s","end":"%s"}`,
					uuid,
					startStr,
					endStr,
				),
			),
		)
		return httptest.NewRequest("GET", "/sessions", body)

	}

	t.Run("successful sessions retrieval", func(t *testing.T) {
		t.Parallel()

		getSessionsFunc, called := makeGetSessions(t, uuid, start, end, sessions, nil)
		handler := makeGetSessionsHandler(getSessionsFunc)

		req := makeRequest(uuid, startStr, endStr)
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusOK, w.Code)
		require.NoError(t, err)
		require.JSONEq(t, string(sessionsJSON), w.Body.String())
		require.True(t, *called)
	})

	t.Run("start time == end time", func(t *testing.T) {
		t.Parallel()

		start := time.Date(2023, 1, 1, 0, 0, 0, 0, time.UTC)
		startStr := "2023-01-01T00:00:00Z"
		end := time.Date(2023, 1, 1, 0, 0, 0, 0, time.UTC)
		endStr := "2023-01-01T00:00:00Z"

		getSessionsFunc, called := makeGetSessions(t, uuid, start, end, sessions, nil)
		handler := makeGetSessionsHandler(getSessionsFunc)

		req := makeRequest(uuid, startStr, endStr)
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusOK, w.Code)
		require.NoError(t, err)
		require.JSONEq(t, string(sessionsJSON), w.Body.String())
		require.True(t, *called)
	})

	t.Run("invalid UUID format", func(t *testing.T) {
		t.Parallel()

		getSessionsFunc, called := makeGetSessions(t, uuid, start, end, sessions, nil)
		handler := makeGetSessionsHandler(getSessionsFunc)

		req := makeRequest("invalid-uuid", startStr, endStr)
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusBadRequest, w.Code)
		require.Contains(t, w.Body.String(), "invalid uuid")
		require.False(t, *called)
	})

	t.Run("start time after end time", func(t *testing.T) {
		t.Parallel()

		getSessionsFunc, called := makeGetSessions(t, uuid, start, end, sessions, nil)
		handler := makeGetSessionsHandler(getSessionsFunc)

		req := makeRequest(uuid, "2023-01-01T00:00:00.000000001Z", "2023-01-01T00:00:00.000000000Z")
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusBadRequest, w.Code)
		require.Contains(t, w.Body.String(), "Start time cannot be after end time")
		require.False(t, *called)
	})
}
