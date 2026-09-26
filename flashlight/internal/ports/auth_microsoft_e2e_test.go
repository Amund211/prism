package ports_test

import (
	"crypto/sha256"
	"encoding/base64"
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
	"github.com/Amund211/flashlight/internal/authresulttoken"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/signing"
)

// fakeMicrosoftChain serves every leg of the chain. Unless approved,
// login_with_xbox 403s the way Mojang does for an unapproved client id.
func fakeMicrosoftChain(t *testing.T, approved bool) (*httptest.Server, func() url.Values) {
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
		if !approved {
			w.WriteHeader(http.StatusForbidden)
			return
		}
		json(w, http.StatusOK, `{"username":"c4a0e8e1-0000-4000-8000-000000000000","roles":[],"access_token":"mc-token","token_type":"Bearer","expires_in":86400}`)
	})
	mux.HandleFunc("GET /entitlements", func(w http.ResponseWriter, r *http.Request) {
		json(w, http.StatusOK, `{"items":[{"name":"product_minecraft","signature":"a"},{"name":"game_minecraft","signature":"b"}],"signature":"s","keyId":"1"}`)
	})
	mux.HandleFunc("GET /profile", func(w http.ResponseWriter, r *http.Request) {
		json(w, http.StatusOK, `{"id":"a937646bf11544c38dbf9ae4a65669a0","name":"Skydeath","skins":[],"capes":[]}`)
	})
	server := httptest.NewServer(mux)
	t.Cleanup(server.Close)

	return server, func() url.Values {
		mu.Lock()
		defer mu.Unlock()
		return tokenForm
	}
}

type microsoftE2E struct {
	start     http.HandlerFunc
	callback  http.HandlerFunc
	results   authresulttoken.Signed
	tokenForm func() url.Values
}

func newMicrosoftE2E(t *testing.T, approved bool) microsoftE2E {
	t.Helper()
	server, tokenForm := fakeMicrosoftChain(t, approved)
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
	keys := [][]byte{[]byte(strings.Repeat("k", signing.MinKeyLength))}
	flows, err := authflowtoken.NewSigned(keys)
	require.NoError(t, err)
	results, err := authresulttoken.NewSigned(keys)
	require.NoError(t, err)

	return microsoftE2E{
		start:     newMicrosoftStartHandler(t, app.BuildStartMicrosoftSignIn(client, flows, time.Now), emptyBlocklistConfig),
		callback:  newMicrosoftCallbackHandler(t, app.BuildFinishMicrosoftSignIn(client, flows, results, time.Now), authTestLogger, noopAuthMiddleware),
		results:   results,
		tokenForm: tokenForm,
	}
}

// signIn runs /start with query, then Microsoft's redirect back with a
// code, and returns the callback's response.
func (e microsoftE2E) signIn(t *testing.T, query string) *httptest.ResponseRecorder {
	t.Helper()
	r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/auth/microsoft/start?"+query, http.NoBody)
	withRequestIP(r, "1.2.3.4")
	w := httptest.NewRecorder()
	e.start(w, r)
	require.Equal(t, http.StatusFound, w.Code)

	authorize, err := url.Parse(w.Header().Get("Location"))
	require.NoError(t, err)
	require.Equal(t, "login.example.com", authorize.Host)
	state := authorize.Query().Get("state")
	require.NotEmpty(t, state)
	flowCookie := findCookie(t, w.Result(), flowCookieName)

	r = httptest.NewRequestWithContext(t.Context(), http.MethodGet,
		"/v1/auth/microsoft/callback?code=the-code&state="+url.QueryEscape(state), http.NoBody)
	withRequestIP(r, "1.2.3.4")
	r.AddCookie(&http.Cookie{Name: flowCookie.Name, Value: flowCookie.Value})
	w = httptest.NewRecorder()
	e.callback(w, r)
	requireFlowCookieCleared(t, w.Result())
	return w
}

// TestMicrosoftTestSignInEndToEnd is goal 1 of the broker plan against
// fakes: /start, Microsoft's redirect back, and a result page showing
// client_not_approved.
func TestMicrosoftTestSignInEndToEnd(t *testing.T) {
	t.Parallel()
	e := newMicrosoftE2E(t, false)

	w := e.signIn(t, "")
	require.Equal(t, http.StatusForbidden, w.Code)
	require.Contains(t, w.Body.String(), "client_not_approved")

	form := e.tokenForm()
	require.Equal(t, "the-code", form.Get("code"))
	require.NotEmpty(t, form.Get("code_verifier"), "the flow's PKCE verifier reaches the token endpoint")
}

func TestMicrosoftClientSignInEndToEnd(t *testing.T) {
	t.Parallel()

	verifier := strings.Repeat("v", 43)
	digest := sha256.Sum256([]byte(verifier))
	challenge := base64.RawURLEncoding.EncodeToString(digest[:])
	account := domain.MinecraftAccount{UUID: "a937646b-f115-44c3-8dbf-9ae4a65669a0", Username: "Skydeath"}

	t.Run("prism gets the result on its loopback", func(t *testing.T) {
		t.Parallel()
		e := newMicrosoftE2E(t, true)

		w := e.signIn(t, "return="+url.QueryEscape("http://127.0.0.1:52345/callback")+"&challenge="+challenge+"&state=nonce")
		require.Equal(t, http.StatusFound, w.Code)
		location, err := url.Parse(w.Header().Get("Location"))
		require.NoError(t, err)
		require.Equal(t, "http://127.0.0.1:52345/callback", location.Scheme+"://"+location.Host+location.Path)
		require.Equal(t, "nonce", location.Query().Get("state"))

		result, err := e.results.Unseal(location.Query().Get("result"))
		require.NoError(t, err)
		require.Equal(t, account, result.Account)
		require.Equal(t, domain.MicrosoftClientPrism, result.ClientType)
		require.Equal(t, challenge, result.Challenge)
	})

	t.Run("rainbow gets the result in the fragment", func(t *testing.T) {
		t.Parallel()
		e := newMicrosoftE2E(t, true)

		w := e.signIn(t, "return="+url.QueryEscape("https://example.com")+"&challenge="+challenge)
		require.Equal(t, http.StatusFound, w.Code)
		location, err := url.Parse(w.Header().Get("Location"))
		require.NoError(t, err)
		require.Equal(t, "https://example.com/auth/microsoft", location.Scheme+"://"+location.Host+location.Path)
		require.Empty(t, location.RawQuery)
		fragment, err := url.ParseQuery(location.Fragment)
		require.NoError(t, err)

		result, err := e.results.Unseal(fragment.Get("result"))
		require.NoError(t, err)
		require.Equal(t, account, result.Account)
		require.Equal(t, domain.MicrosoftClientRainbow, result.ClientType)
		require.Equal(t, challenge, result.Challenge)
	})

	t.Run("an unapproved client id is sent back as an error", func(t *testing.T) {
		t.Parallel()
		e := newMicrosoftE2E(t, false)

		w := e.signIn(t, "return="+url.QueryEscape("http://127.0.0.1:52345/callback")+"&challenge="+challenge+"&state=nonce")
		require.Equal(t, http.StatusFound, w.Code)
		require.Equal(t, "http://127.0.0.1:52345/callback?error=client_not_approved&state=nonce", w.Header().Get("Location"))
	})
}
