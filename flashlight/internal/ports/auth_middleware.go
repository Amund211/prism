package ports

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"time"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
)

type authSessionCtxKey struct{}

// AuthContext is what the bearer middleware stashes into the request
// context when a valid Authorization header is present. Absent when the
// request had no Authorization header (legacy X-User-Id callers).
type AuthContext struct {
	SessionID    string
	IdentityType domain.AuthSessionIdentityType
	IdentityKey  string
}

// AuthFromContext returns the auth context attached by the bearer
// middleware, or (zero, false) when no bearer was sent.
func AuthFromContext(ctx context.Context) (AuthContext, bool) {
	v, ok := ctx.Value(authSessionCtxKey{}).(AuthContext)
	return v, ok
}

// NewBearerAuthMiddleware returns a middleware that validates an
// Authorization: Bearer <session-id> header against the auth session
// store when present. It is passive: requests without an Authorization
// header pass through unchanged (preserving the legacy X-User-Id
// flow). When a header IS present but the session is unknown or
// expired, the request is rejected with 401 — otherwise a bearer
// would be silently ignored, which would let clients downgrade to the
// un-authenticated path just by sending a bad token.
//
// Where to mount it: behind the blocklist and the IP rate limiters, and
// inside CORS, but ahead of the user-id rate limiter. Validating a bearer
// opens a SELECT-FOR-UPDATE transaction on the session row, and failed
// validations are deliberately never cached, so a garbage token in front
// of the limiters buys an unthrottled DB transaction per request —
// connection-pool exhaustion from a single host, and invisible in the
// metrics if the 401 also short-circuits above the metrics middleware.
// Inside CORS so a 401 keeps its Access-Control-Allow-Origin header and
// the browser can read it rather than reporting an opaque network error.
// Ahead of the user-id limiter so that limiter can key on the verified
// identity from the auth context instead of the self-asserted X-User-Id
// header.
//
// On a successful validation it also sets AuthRefreshHeader when the
// session is due for a refresh, which is what keeps refresh timing
// server-side policy for clients already in users' hands.
func NewBearerAuthMiddleware(validate app.ValidateSession, nowFunc func() time.Time) func(http.HandlerFunc) http.HandlerFunc {
	return func(next http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			rawAuth := r.Header.Get("Authorization")
			if rawAuth == "" {
				next(w, r)
				return
			}

			sessionID, ok := bearerFromAuthorization(r)
			if !ok {
				http.Error(w, "Malformed Authorization header", http.StatusUnauthorized)
				return
			}

			ctx := r.Context()
			view, err := validate(ctx, sessionID)
			switch {
			case errors.Is(err, domain.ErrAuthSessionNotFound),
				errors.Is(err, domain.ErrAuthSessionRevoked),
				errors.Is(err, domain.ErrAuthSessionExpired):
				http.Error(w, "Invalid or expired session", http.StatusUnauthorized)
				return
			case err != nil:
				logging.FromContext(ctx).ErrorContext(ctx, "Failed to validate bearer session", "error", err.Error())
				http.Error(w, "Internal server error", http.StatusInternalServerError)
				return
			}

			if shouldHintRefresh(view, nowFunc()) {
				w.Header().Set(AuthRefreshHeader, "1")
			}

			authCtx := AuthContext{
				SessionID:    view.ID,
				IdentityType: view.IdentityType,
				IdentityKey:  view.IdentityKey,
			}
			ctx = context.WithValue(ctx, authSessionCtxKey{}, authCtx)
			ctx = logging.AddMetaToContext(ctx,
				slog.String("authTier", string(authCtx.IdentityType)),
				slog.String("authIdentityKey", authCtx.IdentityKey),
			)
			next(w, r.WithContext(ctx))
		}
	}
}
