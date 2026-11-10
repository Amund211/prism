package ports_test

import (
	"bytes"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/jmoiron/sqlx"
	"github.com/lib/pq"
	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/adapters/credentialrepository"
	"github.com/Amund211/flashlight/internal/adapters/database"
	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/authsessionguard"
	"github.com/Amund211/flashlight/internal/ports"
)

type credentialLifecycle struct {
	microsoftE2E
	now         time.Time
	exchange    http.HandlerFunc
	recover     http.HandlerFunc
	logout      http.HandlerFunc
	credentials http.HandlerFunc
	db          *sqlx.DB
	schema      string
	logs        *bytes.Buffer
}

func newCredentialLifecycle(t *testing.T, schemaSuffix string) *credentialLifecycle {
	t.Helper()
	db, err := database.NewPostgresDatabase(database.LocalConnectionString)
	require.NoError(t, err)
	t.Cleanup(func() { _ = db.Close() })
	schema := "credential_lifecycle_test_" + schemaSuffix
	db.MustExec(fmt.Sprintf("DROP SCHEMA IF EXISTS %s CASCADE", pq.QuoteIdentifier(schema)))
	require.NoError(t, database.NewDatabaseMigrator(db, slog.New(slog.NewJSONHandler(os.Stdout, nil))).Migrate(t.Context(), schema))
	repo := credentialrepository.NewPostgres(db, schema)

	c := &credentialLifecycle{microsoftE2E: newMicrosoftE2E(t, true), now: time.Now().Truncate(time.Microsecond), db: db, schema: schema, logs: &bytes.Buffer{}}
	clock := func() time.Time { return c.now }
	logger := slog.New(slog.NewJSONHandler(c.logs, nil))

	exchange, stopExchange := ports.MakeMicrosoftSignInExchangeHandler(
		app.BuildExchangeMicrosoftSignIn(c.results, repo, c.sessions, authsessionguard.AllowAll{}, clock, app.GenerateLineage),
		clock, authTestOrigins(t), logger, noopAuthMiddleware, emptyBlocklistConfig,
	)
	t.Cleanup(stopExchange)
	recoverSession, stopRecover := ports.MakeAuthRecoverHandler(
		app.BuildRecoverMicrosoftSession(repo, c.sessions, authsessionguard.AllowAll{}, clock, app.GenerateLineage),
		clock, authTestOrigins(t), logger, noopAuthMiddleware, emptyBlocklistConfig,
	)
	t.Cleanup(stopRecover)
	logout, stopLogout := ports.MakeAuthLogoutHandler(
		app.BuildLogoutMicrosoft(repo),
		authTestOrigins(t), logger, noopAuthMiddleware, emptyBlocklistConfig,
	)
	t.Cleanup(stopLogout)
	credentials, stopCredentials := ports.MakeAuthCredentialsHandler(
		app.BuildListMicrosoftSignIns(repo, clock),
		authTestOrigins(t), logger, noopAuthMiddleware,
		ports.NewBearerAuthMiddleware(app.BuildValidateSession(c.sessions, clock), clock, emptyBlocklistConfig),
		emptyBlocklistConfig,
	)
	t.Cleanup(stopCredentials)

	c.exchange, c.recover, c.logout, c.credentials = exchange, recoverSession, logout, credentials
	return c
}

const signInTimeLayout = "2006-01-02T15:04:05.000000Z07:00"

type listedSignIn struct {
	ClientType string `json:"clientType"`
	CreatedAt  string `json:"createdAt"`
	LastUsedAt string `json:"lastUsedAt"`
}

func (c *credentialLifecycle) listSignIns(t *testing.T, bearer string) (*httptest.ResponseRecorder, []listedSignIn) {
	t.Helper()
	r := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/auth/credentials", http.NoBody)
	withRequestIP(r, "1.2.3.4")
	r.Header.Set("Authorization", "Bearer "+bearer)
	w := httptest.NewRecorder()
	c.credentials(w, r)
	if w.Code != http.StatusOK {
		return w, nil
	}
	var body struct {
		Credentials []listedSignIn `json:"credentials"`
	}
	require.NoError(t, json.Unmarshal(w.Body.Bytes(), &body))
	require.NotNil(t, body.Credentials)
	return w, body.Credentials
}

func (c *credentialLifecycle) rowCount(t *testing.T) int {
	t.Helper()
	var count int
	require.NoError(t, c.db.GetContext(t.Context(), &count, fmt.Sprintf("SELECT count(*) FROM %s.user_credentials", pq.QuoteIdentifier(c.schema))))
	return count
}

func (c *credentialLifecycle) signInAndExchange(t *testing.T, target string) *httptest.ResponseRecorder {
	t.Helper()
	verifier := strings.Repeat("v", 43)
	digest := sha256.Sum256([]byte(verifier))
	challenge := base64.RawURLEncoding.EncodeToString(digest[:])

	query := "return=" + url.QueryEscape(target) + "&challenge=" + challenge
	origin := target
	if strings.HasPrefix(target, "http://127.0.0.1") {
		query += "&state=nonce"
		origin = ""
	}
	w := c.signIn(t, query)
	require.Equal(t, http.StatusFound, w.Code)
	location, err := url.Parse(w.Header().Get("Location"))
	require.NoError(t, err)
	result := location.Query().Get("result")
	if result == "" {
		fragment, err := url.ParseQuery(location.Fragment)
		require.NoError(t, err)
		result = fragment.Get("result")
	}
	require.NotEmpty(t, result)

	r := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/v1/auth/microsoft/exchange", strings.NewReader(exchangeBody(result, verifier)))
	withRequestIP(r, "1.2.3.4")
	withJSONContentType(r)
	if origin != "" {
		r.Header.Set("Origin", origin)
	}
	w = httptest.NewRecorder()
	c.exchange(w, r)
	c.requireMicrosoftSession(t, w)
	return w
}

func (c *credentialLifecycle) prismRecover(t *testing.T, credential string) *httptest.ResponseRecorder {
	t.Helper()
	w := httptest.NewRecorder()
	c.recover(w, credentialRequest(t, "/v1/auth/recover", credentialBody(credential), ""))
	return w
}

func bodyCredential(t *testing.T, w *httptest.ResponseRecorder) string {
	t.Helper()
	var body map[string]any
	require.NoError(t, json.Unmarshal(w.Body.Bytes(), &body))
	credential, ok := body["credential"].(string)
	require.True(t, ok)
	return credential
}

func TestCredentialLifecycleEndToEnd(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping db tests in short mode.")
	}
	t.Parallel()

	t.Run("prism rotates on use with a one-minute grace window", func(t *testing.T) {
		t.Parallel()
		c := newCredentialLifecycle(t, "prism_rotation")
		first := bodyCredential(t, c.signInAndExchange(t, "http://127.0.0.1:52345/callback"))

		w := c.prismRecover(t, first)
		c.requireMicrosoftSession(t, w)
		second := bodyCredential(t, w)
		require.NotEqual(t, first, second)

		c.now = c.now.Add(59 * time.Second)
		w = c.prismRecover(t, first)
		c.requireMicrosoftSession(t, w)
		require.NotEqual(t, second, bodyCredential(t, w), "a grace-window recover still rotates")

		c.now = c.now.Add(2 * time.Second)
		require.Equal(t, http.StatusUnauthorized, c.prismRecover(t, first).Code, "past the grace window the old value is dead")

		c.now = c.now.Add(80 * 24 * time.Hour)
		w = c.prismRecover(t, second)
		c.requireMicrosoftSession(t, w)
		third := bodyCredential(t, w)

		c.now = c.now.Add(89 * 24 * time.Hour)
		c.requireMicrosoftSession(t, c.prismRecover(t, third))
		require.Equal(t, 5, c.rowCount(t), "stale rows are kept until a reaper exists")
	})

	t.Run("rainbow recovers with fl_rm", func(t *testing.T) {
		t.Parallel()
		c := newCredentialLifecycle(t, "rainbow_rotation")
		first := findCookie(t, c.signInAndExchange(t, "https://example.com").Result(), rememberMeCookieName).Value

		r := credentialRequest(t, "/v1/auth/recover", `{}`, first)
		r.Header.Set("Origin", "https://example.com")
		w := httptest.NewRecorder()
		c.recover(w, r)
		c.requireMicrosoftSession(t, w)
		cookie := findCookie(t, w.Result(), rememberMeCookieName)
		require.NotEqual(t, first, cookie.Value)
		require.Equal(t, 7776000, cookie.MaxAge)

		w = c.prismRecover(t, cookie.Value)
		require.Equal(t, http.StatusUnauthorized, w.Code, "rainbow's cookie in a body is refused")
		w = httptest.NewRecorder()
		c.recover(w, credentialRequest(t, "/v1/auth/recover", `{}`, cookie.Value))
		c.requireMicrosoftSession(t, w)
	})

	t.Run("logout deletes every credential of the identity", func(t *testing.T) {
		t.Parallel()
		c := newCredentialLifecycle(t, "logout")
		prism := bodyCredential(t, c.signInAndExchange(t, "http://127.0.0.1:52345/callback"))
		rainbow := findCookie(t, c.signInAndExchange(t, "https://example.com").Result(), rememberMeCookieName).Value
		stale := prism
		w := c.prismRecover(t, prism)
		c.requireMicrosoftSession(t, w)
		prism = bodyCredential(t, w)
		require.Equal(t, 3, c.rowCount(t))

		c.now = c.now.Add(2 * time.Minute)
		require.Equal(t, http.StatusUnauthorized, c.prismRecover(t, stale).Code)
		w = httptest.NewRecorder()
		c.logout(w, credentialRequest(t, "/v1/auth/logout", credentialBody(stale), ""))
		require.Equal(t, http.StatusNoContent, w.Code, "a victim holding only a stale value can still log out")
		require.Zero(t, c.rowCount(t))

		require.Equal(t, http.StatusUnauthorized, c.prismRecover(t, prism).Code)
		w = httptest.NewRecorder()
		c.recover(w, credentialRequest(t, "/v1/auth/recover", `{}`, rainbow))
		require.Equal(t, http.StatusUnauthorized, w.Code, "the other client is signed out too")

		w = httptest.NewRecorder()
		c.logout(w, credentialRequest(t, "/v1/auth/logout", `{}`, rainbow))
		require.Equal(t, http.StatusUnauthorized, w.Code)
		requireRememberMeCleared(t, w.Result())
	})

	t.Run("the sign-ins view lists each live sign-in once", func(t *testing.T) {
		t.Parallel()
		c := newCredentialLifecycle(t, "credentials")
		signedInAt := c.now

		w := c.signInAndExchange(t, "http://127.0.0.1:52345/callback")
		prism := bodyCredential(t, w)
		bearer := c.requireMicrosoftSession(t, w)["sessionId"].(string)
		c.now = c.now.Add(10 * time.Second)
		w = c.signInAndExchange(t, "https://example.com")
		rainbow := findCookie(t, w.Result(), rememberMeCookieName).Value
		rainbowBearer := c.requireMicrosoftSession(t, w)["sessionId"].(string)

		w, listed := c.listSignIns(t, bearer)
		require.Equal(t, http.StatusOK, w.Code)
		require.Equal(t, []listedSignIn{
			{"rainbow", signedInAt.Add(10 * time.Second).UTC().Format(signInTimeLayout), signedInAt.Add(10 * time.Second).UTC().Format(signInTimeLayout)},
			{"prism", signedInAt.UTC().Format(signInTimeLayout), signedInAt.UTC().Format(signInTimeLayout)},
		}, listed)
		secrets := []string{prism, rainbow, bearer, rainbowBearer}

		c.now = c.now.Add(5 * time.Minute)
		w = c.prismRecover(t, prism)
		secrets = append(secrets, bodyCredential(t, w), c.requireMicrosoftSession(t, w)["sessionId"].(string))
		c.now = c.now.Add(30 * time.Second)
		w = c.prismRecover(t, prism)
		secrets = append(secrets, bodyCredential(t, w), c.requireMicrosoftSession(t, w)["sessionId"].(string))
		require.Equal(t, 4, c.rowCount(t))

		_, listed = c.listSignIns(t, rainbowBearer)
		require.Len(t, listed, 2, "the grace row and a racing second successor are not more prism sign-ins")
		require.Equal(t, listedSignIn{"prism", signedInAt.UTC().Format(signInTimeLayout), c.now.UTC().Format(signInTimeLayout)}, listed[1])

		anonymous, err := app.BuildAnonymousLogin(c.sessions, authsessionguard.AllowAll{}, func() time.Time { return c.now }, app.GenerateLineage)(t.Context(), "a937646bf11544c38dbf9ae4a65669a0", "iphash")
		require.NoError(t, err)
		w, _ = c.listSignIns(t, anonymous.ID)
		require.Equal(t, http.StatusForbidden, w.Code, "an anonymous session under the same key sees nothing")

		w = httptest.NewRecorder()
		c.logout(w, credentialRequest(t, "/v1/auth/logout", `{}`, rainbow))
		require.Equal(t, http.StatusNoContent, w.Code)
		w, listed = c.listSignIns(t, bearer)
		require.Equal(t, http.StatusOK, w.Code, "logout does not end live sessions")
		require.Empty(t, listed, "and the view says the lever worked")

		require.NotEmpty(t, c.logs.String())
		for _, secret := range secrets {
			digest := sha256.Sum256([]byte(secret))
			for _, s := range []string{secret, hex.EncodeToString(digest[:]), base64.StdEncoding.EncodeToString(digest[:]), base64.RawURLEncoding.EncodeToString(digest[:])} {
				require.NotContains(t, c.logs.String(), s)
			}
		}
	})
}
