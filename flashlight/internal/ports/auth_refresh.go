package ports

import (
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"time"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/reporting"
)

// MakeAuthRefreshHandler returns a handler for POST /v1/auth/refresh.
// Accepts a Bearer token (which may be past expires_at but within
// refresh_until). Tier-agnostic: the underlying use case branches on
// the stored session.
func MakeAuthRefreshHandler(
	refresh app.RefreshSession,
	nowFunc func() time.Time,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
	blocklistConfig BlocklistConfig,
) http.HandlerFunc {
	middleware := ComposeMiddlewares(
		NewRequestLoggerMiddleware(rootLogger),
		sentryMiddleware,
		BuildBlocklistMiddleware(blocklistConfig),
		buildMetricsMiddleware("auth-refresh"),
		NewReportingMetaMiddleware("auth-refresh"),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		sessionID, ok := bearerFromAuthorization(r)
		if !ok {
			http.Error(w, "Missing bearer token", http.StatusUnauthorized)
			return
		}

		ipHash := GetIP(r).Hash()

		view, err := refresh(ctx, sessionID, ipHash)
		switch {
		case errors.Is(err, domain.ErrAuthSessionNotFound),
			errors.Is(err, domain.ErrAuthSessionRevoked),
			errors.Is(err, domain.ErrAuthSessionRefreshExpired):
			http.Error(w, "Session is no longer refreshable", http.StatusUnauthorized)
			return
		case err != nil:
			logging.FromContext(ctx).ErrorContext(ctx, "Session refresh failed", "error", err.Error())
			reporting.Report(ctx, fmt.Errorf("session refresh: %w", err))
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}

		writeAuthSessionResponse(ctx, w, view, nowFunc())
	}

	return middleware(handler)
}
