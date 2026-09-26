package ports

import (
	"context"
	"errors"
	"fmt"
	"html/template"
	"log/slog"
	"net/http"
	"net/url"
	"regexp"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
)

// microsoftFlowCookieName: __Host- makes the browser refuse the cookie
// unless it is Secure, Path=/ and has no Domain, so no other host under
// prismoverlay.com can plant one.
const microsoftFlowCookieName = "__Host-fl_flow"

// newMicrosoftSignInIPLimiter is one sign-in's worth of requests with room
// for retries. A person signs in rarely.
func newMicrosoftSignInIPLimiter() (ratelimiting.RequestRateLimiter, func()) {
	limiter, stop := ratelimiting.NewTokenBucketRateLimiter(
		ratelimiting.RefillPerSecond(0.1),
		ratelimiting.BurstSize(20),
	)
	return ratelimiting.NewRequestBasedRateLimiter(limiter, IPHashKeyFunc), stop
}

// MakeMicrosoftSignInStartHandler returns a handler for
// GET /v1/auth/microsoft/start: set the flow cookie, 302 to Microsoft.
// A top-level navigation, so no CORS.
func MakeMicrosoftSignInStartHandler(
	start app.StartMicrosoftSignIn,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
	blocklistConfig BlocklistConfig,
) (http.HandlerFunc, func()) {
	ipRateLimiter, stop := newMicrosoftSignInIPLimiter()

	middleware := ComposeMiddlewares(
		NewRequestLoggerMiddleware(rootLogger),
		sentryMiddleware,
		BuildBlocklistMiddleware(blocklistConfig),
		buildMetricsMiddleware("auth-microsoft-start"),
		NewReportingMetaMiddleware("auth-microsoft-start"),
		NewRateLimitMiddleware(ipRateLimiter, makeOnAuthLimitExceeded(ipRateLimiter)),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		// TODO: return + challenge for the rainbow and prism flows (phase 3).
		if r.URL.Query().Has("return") {
			http.Error(w, "return is not supported", http.StatusBadRequest)
			return
		}

		started, err := start(ctx)
		if err != nil {
			logging.FromContext(ctx).ErrorContext(ctx, "Failed to start Microsoft sign-in", "error", err.Error())
			reporting.Report(ctx, fmt.Errorf("start microsoft sign-in: %w", err))
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}

		http.SetCookie(w, &http.Cookie{
			Name:     microsoftFlowCookieName,
			Value:    started.FlowCookie,
			Path:     "/",
			MaxAge:   int(started.ExpiresIn.Seconds()),
			Secure:   true,
			HttpOnly: true,
			// Lax, not Strict: the cookie must ride the top-level
			// redirect back from Microsoft.
			SameSite: http.SameSiteLaxMode,
		})
		w.Header().Set("Cache-Control", "no-store")
		http.Redirect(w, r, started.AuthorizeURL, http.StatusFound)
	}

	return middleware(handler), stop
}

type callbackQueryKey struct{}

// hideQuery moves the query into the context and drops it from the
// request, ahead of everything else. The callback's query holds the code
// and state; sentryhttp attaches the query string to every event, and
// GetIP reports the URL.
func hideQuery(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		query := r.URL.Query()
		hidden := r.Clone(context.WithValue(r.Context(), callbackQueryKey{}, query))
		hidden.URL.RawQuery = ""
		hidden.URL.ForceQuery = false
		hidden.RequestURI = hidden.URL.RequestURI()
		next(w, hidden)
	}
}

func callbackQuery(r *http.Request) url.Values {
	query, _ := r.Context().Value(callbackQueryKey{}).(url.Values)
	return query
}

// microsoftErrorRx bounds what of Microsoft's own error code is logged.
var microsoftErrorRx = regexp.MustCompile(`^[a-z_]{1,64}$`)

// MakeMicrosoftSignInCallbackHandler returns a handler for
// GET /v1/auth/microsoft/callback, Microsoft's redirect target. It clears
// the flow cookie and renders the result page, whatever the outcome.
func MakeMicrosoftSignInCallbackHandler(
	finish app.FinishMicrosoftSignIn,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
	blocklistConfig BlocklistConfig,
) (http.HandlerFunc, func()) {
	ipRateLimiter, stop := newMicrosoftSignInIPLimiter()

	middleware := ComposeMiddlewares(
		hideQuery,
		NewRequestLoggerMiddleware(rootLogger),
		sentryMiddleware,
		BuildBlocklistMiddleware(blocklistConfig),
		buildMetricsMiddleware("auth-microsoft-callback"),
		NewReportingMetaMiddleware("auth-microsoft-callback"),
		NewRateLimitMiddleware(ipRateLimiter, makeOnAuthLimitExceeded(ipRateLimiter)),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		logger := logging.FromContext(ctx)

		// One flow per cookie, whatever happens next.
		http.SetCookie(w, &http.Cookie{
			Name:     microsoftFlowCookieName,
			Value:    "",
			Path:     "/",
			MaxAge:   -1,
			Secure:   true,
			HttpOnly: true,
			SameSite: http.SameSiteLaxMode,
		})

		query := callbackQuery(r)
		if query.Has("error") {
			microsoftError := query.Get("error")
			if !microsoftErrorRx.MatchString(microsoftError) {
				microsoftError = "<unrecognized>"
			}
			logger.InfoContext(ctx, "Microsoft sign-in refused by Microsoft", "outcome", "microsoft_error", "microsoftError", microsoftError)
			renderMicrosoftSignInResult(ctx, w, http.StatusBadRequest, signInResult{Code: "microsoft_error"})
			return
		}
		code, state := query.Get("code"), query.Get("state")
		if code == "" || state == "" {
			logger.InfoContext(ctx, "Microsoft sign-in callback without code or state", "outcome", "invalid_callback")
			renderMicrosoftSignInResult(ctx, w, http.StatusBadRequest, signInResult{Code: "invalid_callback"})
			return
		}

		flowCookie := ""
		if cookie, err := r.Cookie(microsoftFlowCookieName); err == nil {
			flowCookie = cookie.Value
		}

		account, err := finish(ctx, flowCookie, state, code)
		if err != nil {
			outcome, status := microsoftSignInOutcome(err)
			// Safe to log and report: no error on this path quotes the
			// cookie, state, code or a token.
			if status == http.StatusInternalServerError {
				logger.ErrorContext(ctx, "Microsoft sign-in failed", "outcome", outcome, "error", err.Error())
				reporting.Report(ctx, fmt.Errorf("microsoft sign-in: %w", err))
			} else {
				logger.InfoContext(ctx, "Microsoft sign-in refused", "outcome", outcome, "error", err.Error())
			}
			renderMicrosoftSignInResult(ctx, w, status, signInResult{Code: outcome})
			return
		}

		logger.InfoContext(ctx, "Microsoft sign-in succeeded", "outcome", "ok", "uuid", account.UUID)
		renderMicrosoftSignInResult(ctx, w, http.StatusOK, signInResult{Username: account.Username})
	}

	return middleware(handler), stop
}

// microsoftSignInOutcome maps a sign-in error to the code the result page
// shows and its status.
func microsoftSignInOutcome(err error) (string, int) {
	for _, o := range []struct {
		err    error
		code   string
		status int
	}{
		{domain.ErrMicrosoftSignInFlowMissing, "flow_missing", http.StatusBadRequest},
		{domain.ErrMicrosoftSignInFlowInvalid, "flow_invalid", http.StatusBadRequest},
		{domain.ErrMicrosoftSignInFlowExpired, "flow_expired", http.StatusBadRequest},
		{domain.ErrMicrosoftSignInStateMismatch, "state_mismatch", http.StatusBadRequest},
		{domain.ErrMicrosoftCodeRejected, "code_rejected", http.StatusBadRequest},
		{domain.ErrXbox, "xbox_refused", http.StatusForbidden},
		{domain.ErrNoXboxAccount, "no_xbox_account", http.StatusForbidden},
		{domain.ErrXboxUnavailableInRegion, "xbox_unavailable_in_region", http.StatusForbidden},
		{domain.ErrAdultVerificationRequired, "adult_verification_required", http.StatusForbidden},
		{domain.ErrChildAccount, "child_account", http.StatusForbidden},
		{domain.ErrClientNotApproved, "client_not_approved", http.StatusForbidden},
		{domain.ErrNoGame, "no_game", http.StatusForbidden},
		{domain.ErrNoProfile, "no_profile", http.StatusForbidden},
		{domain.ErrTemporarilyUnavailable, "temporarily_unavailable", http.StatusServiceUnavailable},
	} {
		if errors.Is(err, o.err) {
			return o.code, o.status
		}
	}
	return "internal_error", http.StatusInternalServerError
}

type signInResult struct {
	// Code is set on failure, Username on success.
	Code     string
	Username string
}

var signInResultTemplate = template.Must(template.New("result").Parse(`<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prism Overlay sign-in</title>
</head>
<body>
{{if .Code}}<p>Sign-in failed: <code>{{.Code}}</code></p>{{else}}<p>Signed in as {{.Username}}</p>{{end}}
</body>
</html>
`))

func renderMicrosoftSignInResult(ctx context.Context, w http.ResponseWriter, status int, result signInResult) {
	header := w.Header()
	header.Set("Content-Type", "text/html; charset=utf-8")
	header.Set("Cache-Control", "no-store")
	// The page URL holds the code.
	header.Set("Referrer-Policy", "no-referrer")
	header.Set("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
	header.Set("X-Content-Type-Options", "nosniff")
	w.WriteHeader(status)
	if err := signInResultTemplate.Execute(w, result); err != nil {
		logging.FromContext(ctx).ErrorContext(ctx, "Failed to write Microsoft sign-in result page", "error", err.Error())
	}
}
