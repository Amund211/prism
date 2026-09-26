package microsoftauth

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"sync"
	"sync/atomic"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/domain"
)

const (
	testClientID     = "test-client-id"
	testClientSecret = "test-client-secret-value"
	testRedirectURI  = "https://flashlight.example.com/v1/auth/microsoft/callback"

	testCode         = "test-authorization-code"
	testCodeVerifier = "test-pkce-verifier"

	testMicrosoftToken = "test-ms-access-token"
	testXboxToken      = "test-xbl-user-token"
	testXSTSToken      = "test-xsts-token"
	testUserHash       = "test-user-hash"
	testMinecraftToken = "test-mc-access-token"
)

// secrets are every value no error, log line or report may contain. The fake
// echoes them back in its error bodies, so a leg that quotes a body fails.
var secrets = []string{
	testClientSecret, testCode, testCodeVerifier,
	testMicrosoftToken, testXboxToken, testXSTSToken, testMinecraftToken,
}

func requireNoSecrets(t *testing.T, s string) {
	t.Helper()
	for _, secret := range secrets {
		require.NotContains(t, s, secret)
	}
}

type recordedRequest struct {
	method string
	header http.Header
	body   []byte
}

// fakeMicrosoft serves all six legs from one httptest server. Each handler
// defaults to the happy path; a test swaps the one it is about.
type fakeMicrosoft struct {
	server *httptest.Server

	mu       sync.Mutex
	handlers map[string]http.HandlerFunc
	requests map[string]recordedRequest
}

const (
	pathToken         = "/consumers/oauth2/v2.0/token"
	pathXboxUser      = "/user/authenticate"
	pathXSTS          = "/xsts/authorize"
	pathLoginWithXbox = "/authentication/login_with_xbox"
	pathEntitlements  = "/entitlements/mcstore"
	pathProfile       = "/minecraft/profile"
)

func respond(status int, body string) http.HandlerFunc {
	return func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		_, _ = io.WriteString(w, body)
	}
}

// echoingSecrets is an error body that quotes every secret, the way a real
// error_description may quote the code it refused.
var echoingSecrets = fmt.Sprintf(`{"error":"server_error","error_description":%q}`, strings.Join(secrets, " "))

func newFakeMicrosoft(t *testing.T) *fakeMicrosoft {
	t.Helper()
	f := &fakeMicrosoft{
		handlers: map[string]http.HandlerFunc{
			pathToken:         respond(http.StatusOK, `{"token_type":"Bearer","scope":"XboxLive.signin","expires_in":3600,"ext_expires_in":3600,"access_token":"`+testMicrosoftToken+`"}`),
			pathXboxUser:      respond(http.StatusOK, `{"IssueInstant":"2026-09-26T12:00:00.0000000Z","NotAfter":"2026-10-10T12:00:00.0000000Z","Token":"`+testXboxToken+`","DisplayClaims":{"xui":[{"uhs":"`+testUserHash+`"}]}}`),
			pathXSTS:          respond(http.StatusOK, `{"IssueInstant":"2026-09-26T12:00:00.0000000Z","NotAfter":"2026-09-27T04:00:00.0000000Z","Token":"`+testXSTSToken+`","DisplayClaims":{"xui":[{"uhs":"`+testUserHash+`"}]}}`),
			pathLoginWithXbox: respond(http.StatusOK, `{"username":"c4a0e8e1-0000-4000-8000-000000000000","roles":[],"access_token":"`+testMinecraftToken+`","token_type":"Bearer","expires_in":86400}`),
			pathEntitlements:  respond(http.StatusOK, `{"items":[{"name":"product_minecraft","signature":"sig1"},{"name":"game_minecraft","signature":"sig2"}],"signature":"sig","keyId":"1"}`),
			pathProfile:       respond(http.StatusOK, `{"id":"a937646bf11544c38dbf9ae4a65669a0","name":"Skydeath","skins":[],"capes":[]}`),
		},
		requests: map[string]recordedRequest{},
	}
	f.server = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, err := io.ReadAll(r.Body)
		if err != nil {
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		f.mu.Lock()
		f.requests[r.URL.Path] = recordedRequest{method: r.Method, header: r.Header.Clone(), body: body}
		handler, ok := f.handlers[r.URL.Path]
		f.mu.Unlock()
		if !ok {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		handler(w, r)
	}))
	t.Cleanup(f.server.Close)
	return f
}

func (f *fakeMicrosoft) handle(path string, handler http.HandlerFunc) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.handlers[path] = handler
}

func (f *fakeMicrosoft) request(t *testing.T, path string) recordedRequest {
	t.Helper()
	f.mu.Lock()
	defer f.mu.Unlock()
	req, ok := f.requests[path]
	require.True(t, ok, "expected a request to %s", path)
	return req
}

func (f *fakeMicrosoft) called(path string) bool {
	f.mu.Lock()
	defer f.mu.Unlock()
	_, ok := f.requests[path]
	return ok
}

func (f *fakeMicrosoft) endpoints() Endpoints {
	return Endpoints{
		Authorize:     "https://login.example.com/consumers/oauth2/v2.0/authorize",
		Token:         f.server.URL + pathToken,
		XboxUser:      f.server.URL + pathXboxUser,
		XSTS:          f.server.URL + pathXSTS,
		LoginWithXbox: f.server.URL + pathLoginWithXbox,
		Entitlements:  f.server.URL + pathEntitlements,
		Profile:       f.server.URL + pathProfile,
	}
}

func newTestClient(t *testing.T, f *fakeMicrosoft) *Client {
	t.Helper()
	client, err := New(f.server.Client(), Config{
		ClientID:     testClientID,
		ClientSecret: testClientSecret,
		RedirectURI:  testRedirectURI,
		Endpoints:    f.endpoints(),
	})
	require.NoError(t, err)
	return client
}

func requireJSON(t *testing.T, expected string, actual []byte) {
	t.Helper()
	require.JSONEq(t, expected, string(actual))
}

func TestNew(t *testing.T) {
	t.Parallel()

	valid := Config{
		ClientID:     testClientID,
		ClientSecret: testClientSecret,
		RedirectURI:  testRedirectURI,
		Endpoints:    DefaultEndpoints(),
	}

	_, err := New(http.DefaultClient, valid)
	require.NoError(t, err)

	_, err = New(nil, valid)
	require.Error(t, err)

	for name, mutate := range map[string]func(*Config){
		"no client id":     func(c *Config) { c.ClientID = "" },
		"no client secret": func(c *Config) { c.ClientSecret = "" },
		"no redirect uri":  func(c *Config) { c.RedirectURI = "" },
		"no endpoints":     func(c *Config) { c.Endpoints = Endpoints{} },
	} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			config := valid
			mutate(&config)
			_, err := New(http.DefaultClient, config)
			require.Error(t, err)
			requireNoSecrets(t, err.Error())
		})
	}
}

func TestDefaultEndpoints(t *testing.T) {
	t.Parallel()

	require.Equal(t, Endpoints{
		Authorize:     "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize",
		Token:         "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
		XboxUser:      "https://user.auth.xboxlive.com/user/authenticate",
		XSTS:          "https://xsts.auth.xboxlive.com/xsts/authorize",
		LoginWithXbox: "https://api.minecraftservices.com/authentication/login_with_xbox",
		Entitlements:  "https://api.minecraftservices.com/entitlements/mcstore",
		Profile:       "https://api.minecraftservices.com/minecraft/profile",
	}, DefaultEndpoints())
}

func TestAuthorizeURL(t *testing.T) {
	t.Parallel()

	client := newTestClient(t, newFakeMicrosoft(t))

	raw := client.AuthorizeURL("the-state", "the-code-challenge")

	u, err := url.Parse(raw)
	require.NoError(t, err)
	require.Equal(t, "https", u.Scheme)
	require.Equal(t, "login.example.com", u.Host)
	require.Equal(t, "/consumers/oauth2/v2.0/authorize", u.Path)
	require.Equal(t, url.Values{
		"client_id":             {testClientID},
		"response_type":         {"code"},
		"redirect_uri":          {testRedirectURI},
		"response_mode":         {"query"},
		"scope":                 {"XboxLive.signin"},
		"state":                 {"the-state"},
		"code_challenge":        {"the-code-challenge"},
		"code_challenge_method": {"S256"},
	}, u.Query(), "exactly these: no offline_access, so no refresh token is ever issued, and no prompt")
	require.NotContains(t, raw, "offline_access")
}

func TestRedeemCode(t *testing.T) {
	t.Parallel()

	t.Run("success", func(t *testing.T) {
		t.Parallel()
		f := newFakeMicrosoft(t)
		client := newTestClient(t, f)

		token, err := client.redeemCode(t.Context(), testCode, testCodeVerifier)
		require.NoError(t, err)
		require.Equal(t, testMicrosoftToken, token.reveal())

		req := f.request(t, pathToken)
		require.Equal(t, http.MethodPost, req.method)
		require.Equal(t, "application/x-www-form-urlencoded", req.header.Get("Content-Type"))
		form, err := url.ParseQuery(string(req.body))
		require.NoError(t, err)
		require.Equal(t, url.Values{
			"client_id":     {testClientID},
			"client_secret": {testClientSecret},
			"grant_type":    {"authorization_code"},
			"code":          {testCode},
			"redirect_uri":  {testRedirectURI},
			"code_verifier": {testCodeVerifier},
			"scope":         {"XboxLive.signin"},
		}, form)
	})

	for _, c := range []struct {
		name   string
		status int
		body   string
		is     error
	}{
		{"invalid_grant is a rejected code", http.StatusBadRequest, `{"error":"invalid_grant","error_description":"AADSTS70008: The provided authorization code has expired. ` + testCode + `"}`, domain.ErrMicrosoftCodeRejected},
		{"invalid_client is unexpected", http.StatusUnauthorized, `{"error":"invalid_client","error_description":"AADSTS7000222: The provided client secret keys are expired. ` + testClientSecret + `"}`, nil},
		{"503 is temporary", http.StatusServiceUnavailable, echoingSecrets, domain.ErrTemporarilyUnavailable},
		{"429 is temporary", http.StatusTooManyRequests, echoingSecrets, domain.ErrTemporarilyUnavailable},
		{"500 with a body quoting secrets", http.StatusInternalServerError, echoingSecrets, domain.ErrTemporarilyUnavailable},
		{"200 without a token", http.StatusOK, `{"token_type":"Bearer"}`, nil},
		{"200 that is not json", http.StatusOK, `not json ` + testMicrosoftToken, nil},
	} {
		t.Run(c.name, func(t *testing.T) {
			t.Parallel()
			f := newFakeMicrosoft(t)
			f.handle(pathToken, respond(c.status, c.body))
			client := newTestClient(t, f)

			_, err := client.redeemCode(t.Context(), testCode, testCodeVerifier)
			require.Error(t, err)
			if c.is != nil {
				require.ErrorIs(t, err, c.is)
			}
			requireNoSecrets(t, err.Error())
		})
	}

	t.Run("invalid_client names the error code", func(t *testing.T) {
		t.Parallel()
		f := newFakeMicrosoft(t)
		f.handle(pathToken, respond(http.StatusUnauthorized, `{"error":"invalid_client"}`))
		client := newTestClient(t, f)

		_, err := client.redeemCode(t.Context(), testCode, testCodeVerifier)
		require.ErrorContains(t, err, "invalid_client", "an expired client secret must be recognisable from the report alone")
	})
}

func TestAuthenticateXbox(t *testing.T) {
	t.Parallel()

	t.Run("success", func(t *testing.T) {
		t.Parallel()
		f := newFakeMicrosoft(t)
		client := newTestClient(t, f)

		token, err := client.authenticateXbox(t.Context(), secret(testMicrosoftToken))
		require.NoError(t, err)
		require.Equal(t, testXboxToken, token.reveal())

		req := f.request(t, pathXboxUser)
		require.Equal(t, http.MethodPost, req.method)
		require.Equal(t, "application/json", req.header.Get("Content-Type"))
		require.Equal(t, "application/json", req.header.Get("Accept"))
		requireJSON(t, `{
			"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": "d=`+testMicrosoftToken+`"},
			"RelyingParty": "http://auth.xboxlive.com",
			"TokenType": "JWT"
		}`, req.body)
	})

	for _, c := range []struct {
		name   string
		status int
		body   string
		is     error
	}{
		{"401 is an xbox refusal", http.StatusUnauthorized, echoingSecrets, domain.ErrXbox},
		{"400 is an xbox refusal", http.StatusBadRequest, echoingSecrets, domain.ErrXbox},
		{"503 is temporary", http.StatusServiceUnavailable, echoingSecrets, domain.ErrTemporarilyUnavailable},
		{"200 without a token", http.StatusOK, `{"DisplayClaims":{"xui":[{"uhs":"x"}]}}`, nil},
	} {
		t.Run(c.name, func(t *testing.T) {
			t.Parallel()
			f := newFakeMicrosoft(t)
			f.handle(pathXboxUser, respond(c.status, c.body))
			client := newTestClient(t, f)

			_, err := client.authenticateXbox(t.Context(), secret(testMicrosoftToken))
			require.Error(t, err)
			if c.is != nil {
				require.ErrorIs(t, err, c.is)
			}
			requireNoSecrets(t, err.Error())
		})
	}
}

func TestAuthorizeXSTS(t *testing.T) {
	t.Parallel()

	t.Run("success", func(t *testing.T) {
		t.Parallel()
		f := newFakeMicrosoft(t)
		client := newTestClient(t, f)

		token, userHash, err := client.authorizeXSTS(t.Context(), secret(testXboxToken))
		require.NoError(t, err)
		require.Equal(t, testXSTSToken, token.reveal())
		require.Equal(t, testUserHash, userHash)

		req := f.request(t, pathXSTS)
		require.Equal(t, http.MethodPost, req.method)
		require.Equal(t, "application/json", req.header.Get("Content-Type"))
		requireJSON(t, `{
			"Properties": {"SandboxId": "RETAIL", "UserTokens": ["`+testXboxToken+`"]},
			"RelyingParty": "rp://api.minecraftservices.com/",
			"TokenType": "JWT"
		}`, req.body)
	})

	xErr := func(code int64) string {
		return fmt.Sprintf(`{"Identity":"0","XErr":%d,"Message":"%s","Redirect":"https://start.ui.xboxlive.com/CreateAccount"}`, code, testXboxToken)
	}

	for _, c := range []struct {
		name   string
		status int
		body   string
		is     error
	}{
		{"2148916233 is no xbox account", http.StatusUnauthorized, xErr(2148916233), domain.ErrNoXboxAccount},
		{"2148916235 is unavailable in region", http.StatusUnauthorized, xErr(2148916235), domain.ErrXboxUnavailableInRegion},
		{"2148916236 needs adult verification", http.StatusUnauthorized, xErr(2148916236), domain.ErrAdultVerificationRequired},
		{"2148916237 needs adult verification", http.StatusUnauthorized, xErr(2148916237), domain.ErrAdultVerificationRequired},
		{"2148916238 is a child account", http.StatusUnauthorized, xErr(2148916238), domain.ErrChildAccount},
		{"an unknown XErr is an xbox refusal", http.StatusUnauthorized, xErr(2148916227), domain.ErrXbox},
		{"401 without a body is an xbox refusal", http.StatusUnauthorized, ``, domain.ErrXbox},
		{"503 is temporary", http.StatusServiceUnavailable, echoingSecrets, domain.ErrTemporarilyUnavailable},
		{"200 without a user hash", http.StatusOK, `{"Token":"x","DisplayClaims":{"xui":[]}}`, nil},
		{"200 without a token", http.StatusOK, `{"DisplayClaims":{"xui":[{"uhs":"x"}]}}`, nil},
	} {
		t.Run(c.name, func(t *testing.T) {
			t.Parallel()
			f := newFakeMicrosoft(t)
			f.handle(pathXSTS, respond(c.status, c.body))
			client := newTestClient(t, f)

			_, _, err := client.authorizeXSTS(t.Context(), secret(testXboxToken))
			require.Error(t, err)
			if c.is != nil {
				require.ErrorIs(t, err, c.is)
			}
			requireNoSecrets(t, err.Error())
		})
	}
}

func TestLoginWithXbox(t *testing.T) {
	t.Parallel()

	t.Run("success", func(t *testing.T) {
		t.Parallel()
		f := newFakeMicrosoft(t)
		client := newTestClient(t, f)

		token, err := client.loginWithXbox(t.Context(), secret(testXSTSToken), testUserHash)
		require.NoError(t, err)
		require.Equal(t, testMinecraftToken, token.reveal())

		req := f.request(t, pathLoginWithXbox)
		require.Equal(t, http.MethodPost, req.method)
		require.Equal(t, "application/json", req.header.Get("Content-Type"))
		requireJSON(t, `{"identityToken": "XBL3.0 x=`+testUserHash+`;`+testXSTSToken+`"}`, req.body)
	})

	for _, c := range []struct {
		name   string
		status int
		body   string
		is     error
	}{
		{"403 is an unapproved client id", http.StatusForbidden, `{"path":"/authentication/login_with_xbox","errorMessage":"Invalid app registration, see https://aka.ms/AppRegInfo for more information"}`, domain.ErrClientNotApproved},
		{"403 quoting secrets", http.StatusForbidden, echoingSecrets, domain.ErrClientNotApproved},
		{"429 is temporary", http.StatusTooManyRequests, echoingSecrets, domain.ErrTemporarilyUnavailable},
		{"401 is unexpected", http.StatusUnauthorized, echoingSecrets, nil},
		{"200 without a token", http.StatusOK, `{"username":"x"}`, nil},
	} {
		t.Run(c.name, func(t *testing.T) {
			t.Parallel()
			f := newFakeMicrosoft(t)
			f.handle(pathLoginWithXbox, respond(c.status, c.body))
			client := newTestClient(t, f)

			_, err := client.loginWithXbox(t.Context(), secret(testXSTSToken), testUserHash)
			require.Error(t, err)
			if c.is != nil {
				require.ErrorIs(t, err, c.is)
			}
			requireNoSecrets(t, err.Error())
		})
	}
}

func TestCheckOwnership(t *testing.T) {
	t.Parallel()

	for _, c := range []struct {
		name   string
		status int
		body   string
		is     error
		ok     bool
	}{
		{"both entitlements", http.StatusOK, `{"items":[{"name":"product_minecraft","signature":"a"},{"name":"game_minecraft","signature":"b"}],"signature":"s","keyId":"1"}`, nil, true},
		{"game only", http.StatusOK, `{"items":[{"name":"game_minecraft","signature":"b"}],"signature":"s","keyId":"1"}`, nil, true},
		{"product only", http.StatusOK, `{"items":[{"name":"product_minecraft","signature":"a"}],"signature":"s","keyId":"1"}`, nil, true},
		{"no items", http.StatusOK, `{"items":[],"signature":"s","keyId":"1"}`, domain.ErrNoGame, false},
		{"other items only", http.StatusOK, `{"items":[{"name":"product_dungeons","signature":"a"}],"signature":"s","keyId":"1"}`, domain.ErrNoGame, false},
		{"503 is temporary", http.StatusServiceUnavailable, echoingSecrets, domain.ErrTemporarilyUnavailable, false},
		{"401 is unexpected", http.StatusUnauthorized, echoingSecrets, nil, false},
		{"200 that is not json", http.StatusOK, `nope ` + testMinecraftToken, nil, false},
	} {
		t.Run(c.name, func(t *testing.T) {
			t.Parallel()
			f := newFakeMicrosoft(t)
			f.handle(pathEntitlements, respond(c.status, c.body))
			client := newTestClient(t, f)

			err := client.checkOwnership(t.Context(), secret(testMinecraftToken))

			req := f.request(t, pathEntitlements)
			require.Equal(t, http.MethodGet, req.method)
			require.Equal(t, "Bearer "+testMinecraftToken, req.header.Get("Authorization"))

			if c.ok {
				require.NoError(t, err)
				return
			}
			require.Error(t, err)
			if c.is != nil {
				require.ErrorIs(t, err, c.is)
			}
			requireNoSecrets(t, err.Error())
		})
	}
}

func TestGetProfile(t *testing.T) {
	t.Parallel()

	t.Run("success", func(t *testing.T) {
		t.Parallel()
		f := newFakeMicrosoft(t)
		client := newTestClient(t, f)

		account, err := client.getProfile(t.Context(), secret(testMinecraftToken))
		require.NoError(t, err)
		require.Equal(t, domain.MinecraftAccount{
			UUID:     "a937646b-f115-44c3-8dbf-9ae4a65669a0",
			Username: "Skydeath",
		}, account)

		req := f.request(t, pathProfile)
		require.Equal(t, http.MethodGet, req.method)
		require.Equal(t, "Bearer "+testMinecraftToken, req.header.Get("Authorization"))
	})

	for _, c := range []struct {
		name   string
		status int
		body   string
		is     error
	}{
		{"404 is no profile", http.StatusNotFound, `{"path":"/minecraft/profile","errorType":"NOT_FOUND","error":"NOT_FOUND","errorMessage":"The server has not found anything matching the request URI"}`, domain.ErrNoProfile},
		{"503 is temporary", http.StatusServiceUnavailable, echoingSecrets, domain.ErrTemporarilyUnavailable},
		{"401 is unexpected", http.StatusUnauthorized, echoingSecrets, nil},
		{"200 with an invalid uuid", http.StatusOK, `{"id":"not-a-uuid","name":"Skydeath"}`, nil},
		{"200 without a name", http.StatusOK, `{"id":"a937646bf11544c38dbf9ae4a65669a0"}`, nil},
	} {
		t.Run(c.name, func(t *testing.T) {
			t.Parallel()
			f := newFakeMicrosoft(t)
			f.handle(pathProfile, respond(c.status, c.body))
			client := newTestClient(t, f)

			_, err := client.getProfile(t.Context(), secret(testMinecraftToken))
			require.Error(t, err)
			if c.is != nil {
				require.ErrorIs(t, err, c.is)
			}
			requireNoSecrets(t, err.Error())
		})
	}
}

func TestSignIn(t *testing.T) {
	t.Parallel()

	t.Run("runs the whole chain", func(t *testing.T) {
		t.Parallel()
		f := newFakeMicrosoft(t)
		client := newTestClient(t, f)

		account, err := client.SignIn(t.Context(), testCode, testCodeVerifier)
		require.NoError(t, err)
		require.Equal(t, domain.MinecraftAccount{
			UUID:     "a937646b-f115-44c3-8dbf-9ae4a65669a0",
			Username: "Skydeath",
		}, account)

		// Each leg is handed the previous leg's token.
		require.Contains(t, string(f.request(t, pathXboxUser).body), "d="+testMicrosoftToken)
		require.Contains(t, string(f.request(t, pathXSTS).body), testXboxToken)
		require.Contains(t, string(f.request(t, pathLoginWithXbox).body), "XBL3.0 x="+testUserHash+";"+testXSTSToken)
		require.Equal(t, "Bearer "+testMinecraftToken, f.request(t, pathEntitlements).header.Get("Authorization"))
		require.Equal(t, "Bearer "+testMinecraftToken, f.request(t, pathProfile).header.Get("Authorization"))
	})

	// The test sign-in before Mojang approves the client ID ends here.
	t.Run("stops at an unapproved client id", func(t *testing.T) {
		t.Parallel()
		f := newFakeMicrosoft(t)
		f.handle(pathLoginWithXbox, respond(http.StatusForbidden, ``))
		client := newTestClient(t, f)

		_, err := client.SignIn(t.Context(), testCode, testCodeVerifier)
		require.ErrorIs(t, err, domain.ErrClientNotApproved)
		requireNoSecrets(t, err.Error())
		require.False(t, f.called(pathEntitlements))
		require.False(t, f.called(pathProfile))
	})

	t.Run("stops at a rejected code", func(t *testing.T) {
		t.Parallel()
		f := newFakeMicrosoft(t)
		f.handle(pathToken, respond(http.StatusBadRequest, `{"error":"invalid_grant"}`))
		client := newTestClient(t, f)

		_, err := client.SignIn(t.Context(), testCode, testCodeVerifier)
		require.ErrorIs(t, err, domain.ErrMicrosoftCodeRejected)
		require.False(t, f.called(pathXboxUser))
	})

	t.Run("stops at no game", func(t *testing.T) {
		t.Parallel()
		f := newFakeMicrosoft(t)
		f.handle(pathEntitlements, respond(http.StatusOK, `{"items":[]}`))
		client := newTestClient(t, f)

		_, err := client.SignIn(t.Context(), testCode, testCodeVerifier)
		require.ErrorIs(t, err, domain.ErrNoGame)
		require.False(t, f.called(pathProfile))
	})

	t.Run("an unreachable endpoint names no secret", func(t *testing.T) {
		t.Parallel()
		f := newFakeMicrosoft(t)
		client := newTestClient(t, f)
		f.server.Close()

		_, err := client.SignIn(t.Context(), testCode, testCodeVerifier)
		require.Error(t, err)
		requireNoSecrets(t, err.Error())
	})

	t.Run("a cancelled context", func(t *testing.T) {
		t.Parallel()
		f := newFakeMicrosoft(t)
		client := newTestClient(t, f)
		ctx, cancel := context.WithCancel(t.Context())
		cancel()

		_, err := client.SignIn(ctx, testCode, testCodeVerifier)
		require.ErrorIs(t, err, context.Canceled)
	})
}

// A 307 or 308 replays the POST body, which holds the client secret, the
// code or a token, to whatever host Location names. No leg ever redirects.
func TestRedirectsAreNotFollowed(t *testing.T) {
	t.Parallel()

	for _, path := range []string{pathToken, pathXboxUser, pathXSTS, pathLoginWithXbox, pathEntitlements, pathProfile} {
		for _, status := range []int{http.StatusFound, http.StatusTemporaryRedirect, http.StatusPermanentRedirect} {
			t.Run(fmt.Sprintf("%s/%d", path, status), func(t *testing.T) {
				t.Parallel()

				var elsewhereCalled atomic.Bool
				elsewhere := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
					elsewhereCalled.Store(true)
				}))
				t.Cleanup(elsewhere.Close)

				f := newFakeMicrosoft(t)
				f.handle(path, func(w http.ResponseWriter, r *http.Request) {
					http.Redirect(w, r, elsewhere.URL+"/steal", status)
				})
				client := newTestClient(t, f)

				_, err := client.SignIn(t.Context(), testCode, testCodeVerifier)
				require.Error(t, err)
				requireNoSecrets(t, err.Error())
				require.False(t, elsewhereCalled.Load(), "the redirect must not be followed")
			})
		}
	}

	t.Run("the caller's client is left alone", func(t *testing.T) {
		t.Parallel()
		shared := &http.Client{}
		_, err := New(shared, Config{
			ClientID:     testClientID,
			ClientSecret: testClientSecret,
			RedirectURI:  testRedirectURI,
			Endpoints:    DefaultEndpoints(),
		})
		require.NoError(t, err)
		require.Nil(t, shared.CheckRedirect, "other adapters share this client and may rely on redirects")
	})
}

func TestSecretIsRedacted(t *testing.T) {
	t.Parallel()

	s := secret(testMinecraftToken)

	for _, verb := range []string{"%v", "%+v", "%#v", "%s", "%q", "%x", "%X"} {
		require.NotContains(t, fmt.Sprintf(verb, s), testMinecraftToken, verb)
		require.NotContains(t, fmt.Sprintf(verb, []secret{s}), testMinecraftToken, "slice with "+verb)
	}

	encoded, err := json.Marshal(map[string]secret{"token": s})
	require.NoError(t, err)
	require.NotContains(t, string(encoded), testMinecraftToken)

	var buf bytes.Buffer
	slog.New(slog.NewJSONHandler(&buf, nil)).Info("msg", "token", s)
	slog.New(slog.NewTextHandler(&buf, nil)).Info("msg", "token", s)
	require.NotContains(t, buf.String(), testMinecraftToken)

	require.Equal(t, testMinecraftToken, s.reveal())
}
