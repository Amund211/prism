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
// GET /v1/auth/microsoft/start?return&challenge&state: set the flow
// cookie, 302 to Microsoft. No return is the test sign-in. A top-level
// navigation, so no CORS.
func MakeMicrosoftSignInStartHandler(
	start app.StartMicrosoftSignIn,
	rainbowOrigins *DomainSuffixes,
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
		buildMetricsMiddleware("auth-microsoft-start"),
		NewReportingMetaMiddleware("auth-microsoft-start"),
		NewRateLimitMiddleware(ipRateLimiter, makeOnAuthLimitExceeded(ipRateLimiter)),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		target, err := parseMicrosoftSignInTarget(hiddenQuery(r), rainbowOrigins)
		if err != nil {
			logging.FromContext(ctx).InfoContext(ctx, "Refused Microsoft sign-in start", "error", err.Error())
			http.Error(w, "Invalid return, challenge or state", http.StatusBadRequest)
			return
		}

		started, err := start(ctx, target)
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

type hiddenQueryKey struct{}

// hideQuery moves the query into the context and drops it from the
// request, ahead of everything else. The callback's query holds the code
// and state, /start's holds prism's nonce; sentryhttp attaches the query
// string to every event, and GetIP reports the URL.
func hideQuery(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		query := r.URL.Query()
		hidden := r.Clone(context.WithValue(r.Context(), hiddenQueryKey{}, query))
		hidden.URL.RawQuery = ""
		hidden.URL.ForceQuery = false
		hidden.RequestURI = hidden.URL.RequestURI()
		next(w, hidden)
	}
}

func hiddenQuery(r *http.Request) url.Values {
	query, _ := r.Context().Value(hiddenQueryKey{}).(url.Values)
	return query
}

// rainbowSignInRoute is the rainbow page that receives #result or #error.
const rainbowSignInRoute = "/auth/microsoft"

// signInRedirect is where a client flow's outcome goes: in the fragment
// for rainbow, so it never reaches a server; in the query for prism's
// loopback listener, with its nonce echoed.
func signInRedirect(target *domain.MicrosoftSignInTarget, params url.Values) string {
	if target.ClientType == domain.MicrosoftClientRainbow {
		return target.URL + rainbowSignInRoute + "#" + params.Encode()
	}
	if target.ClientState != "" {
		params.Set("state", target.ClientState)
	}
	return target.URL + "?" + params.Encode()
}

func redirectSignIn(w http.ResponseWriter, r *http.Request, target *domain.MicrosoftSignInTarget, params url.Values) {
	header := w.Header()
	header.Set("Cache-Control", "no-store")
	header.Set("Referrer-Policy", "no-referrer")
	http.Redirect(w, r, signInRedirect(target, params), http.StatusFound)
}

// microsoftErrorRx bounds what of Microsoft's own error code is logged.
var microsoftErrorRx = regexp.MustCompile(`^[a-z_]{1,64}$`)

// MakeMicrosoftSignInCallbackHandler returns a handler for
// GET /v1/auth/microsoft/callback, Microsoft's redirect target. It clears
// the flow cookie, then redirects a client flow's result or error to its
// target, or renders the result page for the test sign-in and for a flow
// that did not verify. It never sets a credential.
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

		query := hiddenQuery(r)
		callback := app.MicrosoftCallback{State: query.Get("state")}
		if cookie, err := r.Cookie(microsoftFlowCookieName); err == nil {
			callback.FlowCookie = cookie.Value
		}
		if query.Has("error") {
			microsoftError := query.Get("error")
			if !microsoftErrorRx.MatchString(microsoftError) {
				microsoftError = "<unrecognized>"
			}
			logger.InfoContext(ctx, "Microsoft sign-in refused by Microsoft", "microsoftError", microsoftError)
			if callback.State == "" {
				logger.InfoContext(ctx, "Microsoft sign-in refused", "outcome", "microsoft_error")
				renderMicrosoftSignInResult(ctx, w, http.StatusBadRequest, signInResult{Code: "microsoft_error"})
				return
			}
			// Verified against the flow so the client learns of it.
			callback.MicrosoftRefused = true
		} else {
			callback.Code = query.Get("code")
			if callback.Code == "" || callback.State == "" {
				logger.InfoContext(ctx, "Microsoft sign-in callback without code or state", "outcome", "invalid_callback")
				renderMicrosoftSignInResult(ctx, w, http.StatusBadRequest, signInResult{Code: "invalid_callback"})
				return
			}
		}

		finished, err := finish(ctx, callback)
		clientType := "none"
		if finished.Target != nil {
			clientType = string(finished.Target.ClientType)
		}
		if err != nil {
			outcome, status := microsoftSignInOutcome(err)
			// Safe to log and report: no error on this path quotes the
			// cookie, state, code or a token.
			if status == http.StatusInternalServerError {
				logger.ErrorContext(ctx, "Microsoft sign-in failed", "outcome", outcome, "clientType", clientType, "error", err.Error())
				reporting.Report(ctx, fmt.Errorf("microsoft sign-in: %w", err))
			} else {
				logger.InfoContext(ctx, "Microsoft sign-in refused", "outcome", outcome, "clientType", clientType, "error", err.Error())
			}
			if finished.Target != nil {
				redirectSignIn(w, r, finished.Target, url.Values{"error": {outcome}})
				return
			}
			renderMicrosoftSignInResult(ctx, w, status, signInResult{Code: outcome})
			return
		}

		logger.InfoContext(ctx, "Microsoft sign-in succeeded", "outcome", "ok", "clientType", clientType, "uuid", finished.Account.UUID)
		if finished.Target != nil {
			redirectSignIn(w, r, finished.Target, url.Values{"result": {finished.Result}})
			return
		}
		renderMicrosoftSignInResult(ctx, w, http.StatusOK, signInResult{Username: finished.Account.Username})
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
		{domain.ErrMicrosoftSignInRefused, "microsoft_error", http.StatusBadRequest},
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
