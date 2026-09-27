package ports_test

import (
	"crypto/sha256"
	"encoding/base64"
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
	now      time.Time
	exchange http.HandlerFunc
	recover  http.HandlerFunc
	logout   http.HandlerFunc
	db       *sqlx.DB
	schema   string
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

	c := &credentialLifecycle{microsoftE2E: newMicrosoftE2E(t, true), now: time.Now().Truncate(time.Microsecond), db: db, schema: schema}
	clock := func() time.Time { return c.now }

	exchange, stopExchange := ports.MakeMicrosoftSignInExchangeHandler(
		app.BuildExchangeMicrosoftSignIn(c.results, repo, c.sessions, authsessionguard.AllowAll{}, clock, app.GenerateLineage),
		clock, authTestOrigins(t), authTestLogger, noopAuthMiddleware, emptyBlocklistConfig,
	)
	t.Cleanup(stopExchange)
	recoverSession, stopRecover := ports.MakeAuthRecoverHandler(
		app.BuildRecoverMicrosoftSession(repo, c.sessions, authsessionguard.AllowAll{}, clock, app.GenerateLineage),
		clock, authTestOrigins(t), authTestLogger, noopAuthMiddleware, emptyBlocklistConfig,
	)
	t.Cleanup(stopRecover)
	logout, stopLogout := ports.MakeAuthLogoutHandler(
		app.BuildLogoutMicrosoft(repo, clock),
		authTestOrigins(t), authTestLogger, noopAuthMiddleware, emptyBlocklistConfig,
	)
	t.Cleanup(stopLogout)

	c.exchange, c.recover, c.logout = exchange, recoverSession, logout
	return c
}

func (c *credentialLifecycle) rowCount(t *testing.T) int {
	t.Helper()
	var count int
	require.NoError(t, c.db.GetContext(t.Context(), &count, fmt.Sprintf("SELECT count(*) FROM %s.user_credentials", pq.QuoteIdentifier(c.schema))))
	return count
}

// signInAndExchange runs a full sign-in for a return target and returns the
// /exchange response.
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
		w := c.prismRecover(t, prism)
		c.requireMicrosoftSession(t, w)
		prism = bodyCredential(t, w)
		require.Equal(t, 3, c.rowCount(t))

		w = httptest.NewRecorder()
		c.logout(w, credentialRequest(t, "/v1/auth/logout", credentialBody(prism), ""))
		require.Equal(t, http.StatusNoContent, w.Code)
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
}
