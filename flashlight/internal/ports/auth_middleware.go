package ports

import (
	"context"
	"errors"
	"log/slog"
	"net/http"

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
func NewBearerAuthMiddleware(validate app.ValidateSession) func(http.HandlerFunc) http.HandlerFunc {
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
