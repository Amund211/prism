package ports

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"mime"
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

// hasJSONContentType reports whether the request declares a JSON body.
// Parameters are allowed (application/json; charset=utf-8); a missing,
// malformed or non-JSON header is not.
func hasJSONContentType(r *http.Request) bool {
	mediaType, _, err := mime.ParseMediaType(r.Header.Get("Content-Type"))
	if err != nil {
		return false
	}
	return mediaType == "application/json"
}

// MakeAnonymousLoginHandler returns a handler for POST /v1/auth/anonymous/login.
// Body: { userId }. Response: a fresh session payload.
func MakeAnonymousLoginHandler(
	login app.AnonymousLogin,
	nowFunc func() time.Time,
	allowedOrigins *DomainSuffixes,
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
		BuildCORSMiddleware(allowedOrigins),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		// Required, not merely accepted: the content type is what keeps
		// this endpoint off the CORS "simple request" path. A POST with
		// text/plain (or no Content-Type at all) carrying a JSON body is
		// dispatched cross-origin without a preflight, so any page on any
		// origin could make a visitor's browser mint sessions from the
		// visitor's IP — enough to walk their ip_hash down the cap in
		// authAnonymousIPCap requests and evict their real sessions. The
		// attacker can't read the response, but it doesn't need to.
		// Requiring application/json forces the preflight, which
		// BuildCORSMiddleware answers only for allowed origins.
		//
		// Refresh needs no equivalent: its Authorization header is not a
		// CORS-safelisted request header, so it is always preflighted.
		if !hasJSONContentType(r) {
			logging.FromContext(ctx).InfoContext(ctx, "Rejected anonymous login with non-JSON content type",
				slog.String("contentType", r.Header.Get("Content-Type")),
			)
			http.Error(w, "Content-Type must be application/json", http.StatusUnsupportedMediaType)
			return
		}

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

		logging.FromContext(ctx).InfoContext(ctx, "Handling auth-anonymous-login request",
			slog.String("bodyUserId", body.UserID),
		)

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
