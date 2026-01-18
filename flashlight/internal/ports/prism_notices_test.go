package ports_test

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"testing/synctest"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/domaintest"
	"github.com/Amund211/flashlight/internal/ports"
	"github.com/stretchr/testify/require"
)

func TestPrismNoticesHandler(t *testing.T) {
	t.Parallel()

	defaultTime := time.Date(2024, time.June, 1, 0, 0, 0, 0, time.UTC)

	cases := []struct {
		userID       string
		prismVersion string
		time         time.Time
		responseJSON string
	}{
		{
			userID:       "",
			prismVersion: "",
			responseJSON: `{"notices":[]}`,
			time:         defaultTime,
		},
		{
			userID:       domaintest.NewUUID(t),
			prismVersion: "v1.10.1-dev",
			responseJSON: `{"notices":[]}`,
			time:         defaultTime,
		},
		{
			userID:       domaintest.NewUUID(t),
			prismVersion: "v1.11.0",
			responseJSON: `{"notices":[]}`,
			time:         defaultTime,
		},
		{
			userID:       domaintest.NewUUID(t),
			prismVersion: "v1.11.0",
			responseJSON: `{"notices":[
				{
					"message":"Click here to view your Prism Wrapped 2025",
					"url":"https://prismoverlay.com/wrapped",
					"severity":"info",
					"duration_seconds":60
				}
			]}`,
			time: time.Date(2025, time.December, 1, 0, 0, 0, 0, time.UTC),
		},
		{
			userID:       domaintest.NewUUID(t),
			prismVersion: "v1.11.0",
			responseJSON: `{"notices":[
				{
					"message":"Click here to view your Prism Wrapped 2025",
					"url":"https://prismoverlay.com/wrapped",
					"severity":"info",
					"duration_seconds":60
				}
			]}`,
			time: time.Date(2025, time.December, 24, 0, 0, 0, 0, time.UTC),
		},
		{
			userID:       domaintest.NewUUID(t),
			prismVersion: "v1.11.0",
			responseJSON: `{"notices":[
				{
					"message":"Click here to view your Prism Wrapped 2025",
					"url":"https://prismoverlay.com/wrapped",
					"severity":"info",
					"duration_seconds":60
				}
			]}`,
			time: time.Date(2026, time.January, 31, 23, 59, 59, 0, time.UTC),
		},
		{
			userID:       domaintest.NewUUID(t),
			prismVersion: "v1.11.0",
			responseJSON: `{"notices":[]}`,
			time:         time.Date(2026, time.February, 1, 0, 0, 0, 0, time.UTC),
		},
	}

	testLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	noopMiddleware := func(h http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			h(w, r)
		}
	}

	// NOTE: Need to make the handler outside, since we create TTL caches inside the handler.
	stubRegisterUserVisit := func(ctx context.Context, userID string) (domain.User, error) {
		return domain.User{}, nil
	}
	handler := ports.MakePrismNoticesHandler(stubRegisterUserVisit, testLogger, noopMiddleware)

	for _, tc := range cases {
		name := fmt.Sprintf("version='%s' userID='%s', time='%s'", tc.prismVersion, tc.userID, tc.time.Format(time.RFC3339))
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			synctest.Test(t, func(t *testing.T) {
				time.Sleep(time.Until(tc.time))

				req := httptest.NewRequest("GET", "/v1/prism-notices", nil)
				req.Header.Set("X-User-Id", tc.userID)
				req.Header.Set("X-Prism-Version", tc.prismVersion)

				w := httptest.NewRecorder()

				handler.ServeHTTP(w, req)

				require.Equal(t, http.StatusOK, w.Code)
				require.JSONEq(t, tc.responseJSON, w.Body.String())
				require.Equal(t, "application/json", w.Result().Header.Get("Content-Type"))
			})
		})
	}
}
