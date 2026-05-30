package ports

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"time"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/reporting"
)

type anonymousLoginRequest struct {
	UserID string `json:"userId"`
}

// userIDMaxLength is the hard cap above which we reject the request.
// The legacy X-User-Id header silently truncates at 50 chars
// (internal/ports/userid.go) and real overlay-generated user_ids are
// 32 chars (uuid4 hex), so 100 is comfortably above expected traffic;
// the over-length report below gives us data to tighten the cap later.
const userIDMaxLength = 100

// userIDWarnLength is the threshold above which we still accept the
// userId but log to Sentry. Anything above 50 is unexpected (matches
// the legacy header truncation point) — keep an eye on real-world
// values before deciding whether to lower the hard cap.
const userIDWarnLength = 50

// MakeAnonymousLoginHandler returns a handler for POST /v1/auth/anonymous/login.
// Body: { userId }. Response: a fresh session payload.
func MakeAnonymousLoginHandler(
	login app.AnonymousLogin,
	nowFunc func() time.Time,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
	blocklistConfig BlocklistConfig,
) http.HandlerFunc {
	middleware := ComposeMiddlewares(
		NewRequestLoggerMiddleware(rootLogger),
		sentryMiddleware,
		BuildBlocklistMiddleware(blocklistConfig),
		buildMetricsMiddleware("auth-anonymous-login"),
		NewReportingMetaMiddleware("auth-anonymous-login"),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		var body anonymousLoginRequest
		if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1024)).Decode(&body); err != nil {
			logging.FromContext(ctx).InfoContext(ctx, "Failed to decode anonymous login body", "error", err.Error())
			http.Error(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		if body.UserID == "" || len(body.UserID) > userIDMaxLength {
			http.Error(w, "Invalid userId", http.StatusBadRequest)
			return
		}
		if len(body.UserID) > userIDWarnLength {
			reporting.Report(
				ctx,
				fmt.Errorf("anonymous login userId longer than expected: len=%d", len(body.UserID)),
			)
		}

		ipHash := GetIP(r).Hash()

		sess, err := login(ctx, body.UserID, ipHash)
		if err != nil {
			logging.FromContext(ctx).ErrorContext(ctx, "Anonymous login failed", "error", err.Error())
			reporting.Report(ctx, fmt.Errorf("anonymous login: %w", err))
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}

		writeAuthSessionResponse(ctx, w, sess, nowFunc())
	}

	return middleware(handler)
}
