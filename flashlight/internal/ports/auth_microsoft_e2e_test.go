package ports_test

import (
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/adapters/microsoftauth"
	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/authflowtoken"
	"github.com/Amund211/flashlight/internal/signing"
)

// fakeMicrosoftChain serves every leg up to login_with_xbox, which 403s the
// way Mojang does for an unapproved client id.
func fakeMicrosoftChain(t *testing.T) (*httptest.Server, func() url.Values) {
	t.Helper()
	var mu sync.Mutex
	var tokenForm url.Values

	json := func(w http.ResponseWriter, status int, body string) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		_, _ = io.WriteString(w, body)
	}
	mux := http.NewServeMux()
	mux.HandleFunc("POST /token", func(w http.ResponseWriter, r *http.Request) {
		require.NoError(t, r.ParseForm())
		mu.Lock()
		tokenForm = r.PostForm
		mu.Unlock()
		json(w, http.StatusOK, `{"token_type":"Bearer","scope":"XboxLive.signin","expires_in":3600,"access_token":"ms-token"}`)
	})
	mux.HandleFunc("POST /user", func(w http.ResponseWriter, r *http.Request) {
		json(w, http.StatusOK, `{"Token":"xbl-token","DisplayClaims":{"xui":[{"uhs":"uhs"}]}}`)
	})
	mux.HandleFunc("POST /xsts", func(w http.ResponseWriter, r *http.Request) {
		json(w, http.StatusOK, `{"Token":"xsts-token","DisplayClaims":{"xui":[{"uhs":"uhs"}]}}`)
	})
	mux.HandleFunc("POST /login_with_xbox", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
	})
	server := httptest.NewServer(mux)
	t.Cleanup(server.Close)

	return server, func() url.Values {
		mu.Lock()
		defer mu.Unlock()
		return tokenForm
	}
}

// TestMicrosoftTestSignInEndToEnd is goal 1 of the broker plan against
// fakes: /start, Microsoft's redirect back, and a result page showing
// client_not_approved.
func TestMicrosoftTestSignInEndToEnd(t *testing.T) {
	t.Parallel()

	server, tokenForm := fakeMicrosoftChain(t)
	client, err := microsoftauth.New(server.Client(), microsoftauth.Config{
		ClientID:     "client-id",
		ClientSecret: "client-secret",
		RedirectURI:  "https://flashlight.example.com/v1/auth/microsoft/callback",
		Endpoints: microsoftauth.Endpoints{
			Authorize:     "https://login.example.com/authorize",
			Token:         server.URL + "/token",
			XboxUser:      server.URL + "/user",
			XSTS:          server.URL + "/xsts",
			LoginWithXbox: server.URL + "/login_with_xbox",
			Entitlements:  server.URL + "/entitlements",
			Profile:       server.URL + "/profile",
		},
	})
	require.NoError(t, err)
	sealer, err := authflowtoken.NewSigned([][]byte{[]byte(strings.Repeat("k", signing.MinKeyLength))})
	require.NoError(t, err)

	startHandler := newMicrosoftStartHandler(t, app.BuildStartMicrosoftSignIn(client, sealer, time.Now), emptyBlocklistConfig)
	callbackHandler := newMicrosoftCallbackHandler(t, app.BuildFinishMicrosoftSignIn(client, sealer, time.Now), authTestLogger, noopAuthMiddleware)

	r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/auth/microsoft/start", http.NoBody)
	withRequestIP(r, "1.2.3.4")
	w := httptest.NewRecorder()
	startHandler(w, r)
	require.Equal(t, http.StatusFound, w.Code)

	authorize, err := url.Parse(w.Header().Get("Location"))
	require.NoError(t, err)
	require.Equal(t, "login.example.com", authorize.Host)
	state := authorize.Query().Get("state")
	require.NotEmpty(t, state)
	flowCookie := findCookie(t, w.Result(), flowCookieName)

	// Microsoft redirects back with a code and the state.
	r = httptest.NewRequestWithContext(t.Context(), http.MethodGet,
		"/v1/auth/microsoft/callback?code=the-code&state="+url.QueryEscape(state), http.NoBody)
	withRequestIP(r, "1.2.3.4")
	r.AddCookie(&http.Cookie{Name: flowCookie.Name, Value: flowCookie.Value})
	w = httptest.NewRecorder()
	callbackHandler(w, r)

	require.Equal(t, http.StatusForbidden, w.Code)
	require.Contains(t, w.Body.String(), "client_not_approved")
	requireFlowCookieCleared(t, w.Result())

	form := tokenForm()
	require.Equal(t, "the-code", form.Get("code"))
	require.NotEmpty(t, form.Get("code_verifier"), "the flow's PKCE verifier reaches the token endpoint")
}
