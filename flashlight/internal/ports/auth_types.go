package ports

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
)

// refreshAtOffset is subtracted from a session's expires_at when
// computing the recommended refresh delay sent to the client.
// Lives here because it's purely a wire-shape concern.
const refreshAtOffset = 5 * time.Minute

// AuthRefreshHeader is set to "1" on responses to bearer-authenticated
// requests whose session the client should now refresh (or re-login, if
// canRefresh said a refresh would be pointless). It is a hint: clients
// that ignore it keep working through the reactive 401 path, which is
// what makes refresh timing changeable server-side after a client ships.
//
// Browsers cannot read it cross-origin unless it is named in
// Access-Control-Expose-Headers — see BuildCORSMiddleware.
const AuthRefreshHeader = "X-Auth-Refresh"

// AuthSessionHeader states the auth disposition of the request that
// produced this response, so a client can attribute a 401 without asking
// the server a second question. It is set by the bearer middleware on
// every request it handled, whatever the handler then returns.
//
// Only AuthSessionValid may be trusted, and only as a statement about
// this one request. Absence means "unknown", not "the session is bad":
// anything answering ahead of the middleware (the blocklist, the IP
// limiters, CORS preflight), anything answering instead of flashlight
// (Cloud Run, the LB), /v1/prestiges/{uuid} which mounts no bearer
// middleware, and a proxy stripping the header all look identical from
// the outside. A client that reads absence as a vouch latches a wrong
// verdict it cannot clear; one that reads it as "unknown" degrades to
// the reactive 401 path it already has.
//
// This is deliberately stricter than the AuthRefreshHeader idiom, where
// any non-empty value counts. Over-reading a hint costs one request;
// over-reading a vouch means believing a session is fine when nothing
// said so.
//
// Browsers cannot read it cross-origin unless it is named in
// Access-Control-Expose-Headers — see BuildCORSMiddleware.
const AuthSessionHeader = "X-Auth-Session"

const (
	// AuthSessionValid means this request carried a bearer that the
	// middleware validated. A 401 alongside it came from the handler and
	// says nothing about the session — /v1/tags rejecting an Urchin API
	// key is the case this exists for.
	AuthSessionValid = "valid"

	// AuthSessionAbsent means the request reached a bearer handler with no
	// Authorization header. Purely diagnostic — it is how a proxy that
	// strips Authorization becomes visible, which it otherwise is not:
	// the server quietly falls back to the X-User-Id path and everything
	// appears to work. No client may branch on it.
	AuthSessionAbsent = "absent"
)

// shouldHintRefresh reports whether to set AuthRefreshHeader for s: the
// client's proactive refresh point (the same one refreshInSeconds counts
// down to) has arrived, and a refresh would not come back a 429. The
// second condition is redundant while refreshAtOffset is well inside
// authMinRefreshInterval, and is here so retuning either one cannot
// start advertising a refresh that gets refused.
func shouldHintRefresh(s domain.AuthSession, now time.Time) bool {
	return !now.Before(s.ExpiresAt.Add(-refreshAtOffset)) && !app.RefreshTooSoon(s, now)
}

// authSessionResponse is the wire shape returned by every session-issuing
// endpoint (login + refresh). The client never needs a wall clock —
// every timing field is a delta from the moment this response was
// produced, so a one-shot setTimeout(refreshInSeconds) is enough.
//
// canRefresh is true while the next refresh would still grant a full
// refresh window; it flips to false on the last refresh whose
// refresh_until got pinned to the absolute lifetime cap. The client
// keeps using the session normally and, when its refresh timer fires,
// does a full re-login instead of calling /refresh.
type authSessionResponse struct {
	SessionID             string `json:"sessionId"`
	Tier                  string `json:"tier"`
	ExpiresInSeconds      int64  `json:"expiresInSeconds"`
	RefreshUntilInSeconds int64  `json:"refreshUntilInSeconds"`
	RefreshInSeconds      int64  `json:"refreshInSeconds"`
	CanRefresh            bool   `json:"canRefresh"`
}

// sessionResponseFromSession derives the wire response from a stored
// session and the moment we're about to send it. All time fields are
// emitted as seconds-from-now so the client never compares timestamps
// against its own clock.
func sessionResponseFromSession(s domain.AuthSession, now time.Time) authSessionResponse {
	refreshAt := s.ExpiresAt.Add(-refreshAtOffset)
	if refreshAt.Before(now) {
		refreshAt = now
	}
	return authSessionResponse{
		SessionID:             s.ID,
		Tier:                  string(s.IdentityType),
		ExpiresInSeconds:      secondsUntil(s.ExpiresAt, now),
		RefreshUntilInSeconds: secondsUntil(s.RefreshUntil, now),
		RefreshInSeconds:      secondsUntil(refreshAt, now),
		CanRefresh:            s.RefreshUntil.Before(s.LifetimeEndsAt),
	}
}

// secondsUntil returns max(0, floor(t - now in seconds)). Negative
// deltas would only happen on a clock anomaly or a session served
// after its expiry; either way we never want to ship a negative
// duration to the client.
func secondsUntil(t, now time.Time) int64 {
	d := int64(t.Sub(now).Seconds())
	if d < 0 {
		return 0
	}
	return d
}

func writeAuthSessionResponse(ctx context.Context, w http.ResponseWriter, sess domain.AuthSession, now time.Time) {
	writeAuthJSONResponse(ctx, w, "session", sessionResponseFromSession(sess, now))
}

// writeAuthJSONResponse writes a 200 with a JSON body. Everything the auth
// endpoints hand out is single-use and caller-specific — a session token, a
// challenge bound to one ip — so no-store is not optional on any of them.
// The what argument names the payload in logs and Sentry reports.
func writeAuthJSONResponse(ctx context.Context, w http.ResponseWriter, what string, body any) {
	data, err := json.Marshal(body)
	if err != nil {
		logging.FromContext(ctx).ErrorContext(ctx, "Failed to marshal auth response", "what", what, "error", err.Error())
		reporting.Report(ctx, fmt.Errorf("marshal %s response: %w", what, err))
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(http.StatusOK)
	if _, err := w.Write(data); err != nil {
		logging.FromContext(ctx).ErrorContext(ctx, "Failed to write auth response", "what", what, "error", err.Error())
		reporting.Report(ctx, fmt.Errorf("write %s response: %w", what, err))
	}
}

// makeOnAuthLimitExceeded is the 429 responder shared by the auth
// endpoints. Same shape as the per-endpoint ones elsewhere; shared here
// because login and refresh want identical behaviour.
func makeOnAuthLimitExceeded(rateLimiter ratelimiting.RequestRateLimiter) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		statusCode := http.StatusTooManyRequests

		logging.FromContext(ctx).InfoContext(ctx, "Rate limit exceeded", "statusCode", statusCode, "reason", "ratelimit exceeded", "key", rateLimiter.KeyFor(r))

		http.Error(w, "Rate limit exceeded", statusCode)
	}
}

// bearerFromAuthorization extracts the bearer token from an Authorization
// header. Case-insensitive on the scheme per RFC 6750. Returns ok=false
// if the header is missing or malformed.
func bearerFromAuthorization(r *http.Request) (string, bool) {
	raw := r.Header.Get("Authorization")
	if raw == "" {
		return "", false
	}
	const prefix = "bearer "
	if len(raw) <= len(prefix) || !strings.EqualFold(raw[:len(prefix)], prefix) {
		return "", false
	}
	token := strings.TrimSpace(raw[len(prefix):])
	if token == "" {
		return "", false
	}
	return token, true
}
