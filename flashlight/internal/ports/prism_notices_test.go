package ports_test

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/domaintest"
	"github.com/Amund211/flashlight/internal/ports"
)

var noopPrismNoticesMiddleware = func(h http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		h(w, r)
	}
}

var stubPrismNoticesRegisterUserVisit = func(ctx context.Context, userID string, ipHash string, userAgent string) (domain.User, error) {
	return domain.User{}, nil
}

var prismNoticesTestLogger = slog.New(slog.NewTextHandler(io.Discard, nil))

func makePrismNoticesHandler(t *testing.T, getPrismNotices app.GetPrismNotices) http.HandlerFunc {
	t.Helper()
	return ports.MakePrismNoticesHandler(
		getPrismNotices,
		stubPrismNoticesRegisterUserVisit,
		prismNoticesTestLogger,
		noopPrismNoticesMiddleware,
		emptyBlocklistConfig,
	)
}

func TestPrismNoticesHandlerPassesArgsToApp(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name                  string
		userID                string
		prismVersionHeader    string
		includeVersionUpdates string
		wantPrismVersion      string
		wantSelection         app.UpdateSelection
	}{
		{
			name:                  "selection=none",
			userID:                domaintest.NewUUID(t),
			prismVersionHeader:    "v1.12.0",
			includeVersionUpdates: "none",
			wantPrismVersion:      "v1.12.0",
			wantSelection:         app.UpdateSelectionNone,
		},
		{
			name:                  "selection=minor",
			userID:                domaintest.NewUUID(t),
			prismVersionHeader:    "v1.12.0",
			includeVersionUpdates: "minor",
			wantPrismVersion:      "v1.12.0",
			wantSelection:         app.UpdateSelectionMinor,
		},
		{
			name:                  "selection=all",
			userID:                domaintest.NewUUID(t),
			prismVersionHeader:    "v1.12.0",
			includeVersionUpdates: "all",
			wantPrismVersion:      "v1.12.0",
			wantSelection:         app.UpdateSelectionAll,
		},
		{
			name:                  "missing query param defaults to all",
			userID:                domaintest.NewUUID(t),
			prismVersionHeader:    "v1.12.0",
			includeVersionUpdates: "",
			wantPrismVersion:      "v1.12.0",
			wantSelection:         app.UpdateSelectionAll,
		},
		{
			name:                  "unrecognized query param defaults to all",
			userID:                domaintest.NewUUID(t),
			prismVersionHeader:    "v1.12.0",
			includeVersionUpdates: "bogus",
			wantPrismVersion:      "v1.12.0",
			wantSelection:         app.UpdateSelectionAll,
		},
		{
			name:                  "missing prism version header is replaced with <missing>",
			userID:                domaintest.NewUUID(t),
			prismVersionHeader:    "",
			includeVersionUpdates: "all",
			wantPrismVersion:      "<missing>",
			wantSelection:         app.UpdateSelectionAll,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			called := false
			getPrismNotices := func(ctx context.Context, userID, prismVersion string, selection app.UpdateSelection) []app.PrismNotice {
				require.False(t, called, "getPrismNotices should be called exactly once")
				called = true
				require.Equal(t, tc.userID, userID)
				require.Equal(t, tc.wantPrismVersion, prismVersion)
				require.Equal(t, tc.wantSelection, selection)
				return []app.PrismNotice{}
			}
			handler := makePrismNoticesHandler(t, getPrismNotices)

			url := "/v1/prism-notices"
			if tc.includeVersionUpdates != "" {
				url += "?includeVersionUpdates=" + tc.includeVersionUpdates
			}
			req := httptest.NewRequestWithContext(t.Context(), "GET", url, nil)
			req.Header.Set("X-User-Id", tc.userID)
			if tc.prismVersionHeader != "" {
				req.Header.Set("X-Prism-Version", tc.prismVersionHeader)
			}

			w := httptest.NewRecorder()
			handler.ServeHTTP(w, req)

			require.Equal(t, http.StatusOK, w.Code)
			require.True(t, called)
		})
	}
}

func TestPrismNoticesHandlerSerializesAppNotices(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name    string
		notices []app.PrismNotice
		want    string
	}{
		{
			name:    "empty slice serializes to empty notices array",
			notices: []app.PrismNotice{},
			want:    `{"notices":[]}`,
		},
		{
			name: "single info notice with url and duration",
			notices: []app.PrismNotice{
				{
					Message:         "Click here to view your Prism Wrapped 2025",
					URL:             "https://prismoverlay.com/wrapped",
					Severity:        app.SeverityInfo,
					DurationSeconds: new(60.0),
				},
			},
			want: `{"notices":[
				{
					"message":"Click here to view your Prism Wrapped 2025",
					"url":"https://prismoverlay.com/wrapped",
					"severity":"info",
					"duration_seconds":60
				}
			]}`,
		},
		{
			name: "update notice",
			notices: []app.PrismNotice{
				{
					Message:         "New update available! Click here to download.",
					URL:             "https://github.com/Amund211/prism/releases/latest/",
					Severity:        app.SeverityUpdate,
					DurationSeconds: new(60.0),
				},
			},
			want: `{"notices":[
				{
					"message":"New update available! Click here to download.",
					"url":"https://github.com/Amund211/prism/releases/latest/",
					"severity":"update",
					"duration_seconds":60
				}
			]}`,
		},
		{
			name: "warning notice with url and duration",
			notices: []app.PrismNotice{
				{
					Message:         "We've detected a potential issue with your Prism client.\nPlease click here to create a ticket in the discord server",
					URL:             "https://discord.gg/NGpRrdh6Fx",
					Severity:        app.SeverityWarning,
					DurationSeconds: new(120.0),
				},
			},
			want: `{"notices":[
				{
					"message":"We've detected a potential issue with your Prism client.\nPlease click here to create a ticket in the discord server",
					"url":"https://discord.gg/NGpRrdh6Fx",
					"severity":"warning",
					"duration_seconds":120
				}
			]}`,
		},
		{
			name: "critical notice without optional fields",
			notices: []app.PrismNotice{
				{
					Message:  "Something critical happened",
					Severity: app.SeverityCritical,
				},
			},
			want: `{"notices":[
				{
					"message":"Something critical happened",
					"severity":"critical"
				}
			]}`,
		},
		{
			name: "multiple notices preserve order",
			notices: []app.PrismNotice{
				{
					Message:         "first",
					Severity:        app.SeverityUpdate,
					DurationSeconds: new(60.0),
				},
				{
					Message:  "second",
					Severity: app.SeverityInfo,
				},
			},
			want: `{"notices":[
				{
					"message":"first",
					"severity":"update",
					"duration_seconds":60
				},
				{
					"message":"second",
					"severity":"info"
				}
			]}`,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			getPrismNotices := func(ctx context.Context, userID, prismVersion string, selection app.UpdateSelection) []app.PrismNotice {
				return tc.notices
			}
			handler := makePrismNoticesHandler(t, getPrismNotices)

			req := httptest.NewRequestWithContext(t.Context(), "GET", "/v1/prism-notices", nil)
			w := httptest.NewRecorder()
			handler.ServeHTTP(w, req)

			require.Equal(t, http.StatusOK, w.Code)
			require.JSONEq(t, tc.want, w.Body.String())
			require.Equal(t, "application/json", w.Result().Header.Get("Content-Type"))
		})
	}
}

func TestPrismNoticesHandlerReturns500OnUnknownSeverity(t *testing.T) {
	t.Parallel()

	getPrismNotices := func(ctx context.Context, userID, prismVersion string, selection app.UpdateSelection) []app.PrismNotice {
		return []app.PrismNotice{
			{
				Message:  "notice with bogus severity",
				Severity: app.Severity("not-a-real-severity"),
			},
		}
	}
	handler := makePrismNoticesHandler(t, getPrismNotices)

	req := httptest.NewRequestWithContext(t.Context(), "GET", "/v1/prism-notices", nil)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)

	require.Equal(t, http.StatusInternalServerError, w.Code)
}
