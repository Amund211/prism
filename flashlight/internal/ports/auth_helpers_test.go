package ports_test

import (
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"io"
	"log/slog"
	"math/bits"
	"net/http"
	"strconv"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/ports"
	"github.com/Amund211/flashlight/internal/proofofwork"
)

var noopAuthMiddleware = func(h http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) { h(w, r) }
}

var authTestLogger = slog.New(slog.NewTextHandler(io.Discard, nil))

const testGCPLoadBalancerIP = "34.111.7.239"

func withRequestIP(r *http.Request, ip string) {
	// GetIP looks at X-Forwarded-For and trims the GCP load-balancer IP
	// from the tail. Setting just the client IP is enough for tests.
	r.Header.Set("X-Forwarded-For", ip+","+testGCPLoadBalancerIP)
}

// withJSONContentType marks the body as JSON. The login handler requires
// it — the header is what forces a CORS preflight — so every test that
// expects to get past that gate has to set it.
func withJSONContentType(r *http.Request) {
	r.Header.Set("Content-Type", "application/json")
}

func authTestOrigins(t *testing.T) *ports.DomainSuffixes {
	t.Helper()
	allowedOrigins, err := ports.NewDomainSuffixes("example.com", "test.com")
	require.NoError(t, err)
	return allowedOrigins
}

// fakeChallenge stands in for a parsed challenge in the tests that aren't
// about proof-of-work. The ones that are build a real scheme.
type fakeChallenge struct {
	difficulty int
	age        time.Duration
	checkErr   error
	onCheck    func(solution string, userID string, ipHash string)
}

func (c fakeChallenge) Difficulty() int    { return c.difficulty }
func (c fakeChallenge) Age() time.Duration { return c.age }

func (c fakeChallenge) Check(solution string, userID string, ipHash string) error {
	if c.onCheck != nil {
		c.onCheck(solution, userID, ipHash)
	}
	return c.checkErr
}

func acceptAnyProof(challenge string) (proofofwork.SignedChallenge, error) {
	return fakeChallenge{}, nil
}

// anonymousLoginBody is a login body whose proof-of-work fields are
// well-formed but meaningless — enough to clear the shape checks when the
// verifier is acceptAnyProof.
func anonymousLoginBody(userID string) string {
	return fmt.Sprintf(`{"userId":%q,"challenge":"challenge-blob","solution":"1"}`, userID)
}

func anonymousChallengeBody(userID string) string {
	return fmt.Sprintf(`{"userId":%q}`, userID)
}

func newAnonymousLoginHandler(t *testing.T, login app.AnonymousLogin, nowFunc func() time.Time) http.HandlerFunc {
	t.Helper()
	return newAnonymousLoginHandlerWithProof(t, login, acceptAnyProof, nowFunc)
}

func newAnonymousLoginHandlerWithProof(t *testing.T, login app.AnonymousLogin, parseChallenge proofofwork.ParseChallenge, nowFunc func() time.Time) http.HandlerFunc {
	t.Helper()
	handler, stop := ports.MakeAnonymousLoginHandler(
		login,
		parseChallenge,
		nowFunc,
		authTestOrigins(t),
		authTestLogger,
		noopAuthMiddleware,
		ports.BlocklistConfig{},
	)
	t.Cleanup(stop)
	return handler
}

// newProofOfWorkScheme wires a real challenge/parse pair sharing one key,
// the way main.go does.
func newProofOfWorkScheme(t *testing.T, difficulty int) (proofofwork.IssueChallenge, proofofwork.ParseChallenge) {
	t.Helper()
	keys, err := proofofwork.ParseSigningKeys([]string{base64.StdEncoding.EncodeToString(make([]byte, 32))})
	require.NoError(t, err)
	difficultyFor, err := proofofwork.BuildDifficultyFunc(difficulty)
	require.NoError(t, err)

	issueChallenge, err := proofofwork.BuildIssueChallenge(keys, difficultyFor, time.Now)
	require.NoError(t, err)
	parseChallenge, err := proofofwork.BuildParseChallenge(keys, time.Now)
	require.NoError(t, err)
	return issueChallenge, parseChallenge
}

// solveChallenge does what a client's worker thread does: hash until the
// digest has enough leading zero bits.
func solveChallenge(t *testing.T, challenge string, difficulty int) string {
	t.Helper()
	for attempt := range 1 << 22 {
		solution := strconv.Itoa(attempt)
		digest := sha256.Sum256([]byte(challenge + ":" + solution))
		zeros := 0
		for _, b := range digest {
			zeros += bits.LeadingZeros8(b)
			if b != 0 {
				break
			}
		}
		if zeros >= difficulty {
			return solution
		}
	}
	t.Fatalf("no solution found for difficulty %d", difficulty)
	return ""
}

func newAnonymousChallengeHandler(t *testing.T, issueChallenge proofofwork.IssueChallenge) http.HandlerFunc {
	t.Helper()
	handler, stop := ports.MakeAnonymousChallengeHandler(
		issueChallenge,
		authTestOrigins(t),
		authTestLogger,
		noopAuthMiddleware,
		ports.BlocklistConfig{},
	)
	t.Cleanup(stop)
	return handler
}

func newAuthRefreshHandler(t *testing.T, refresh app.RefreshSession, nowFunc func() time.Time) http.HandlerFunc {
	t.Helper()
	handler, stop := ports.MakeAuthRefreshHandler(
		refresh,
		nowFunc,
		authTestOrigins(t),
		authTestLogger,
		noopAuthMiddleware,
		ports.BlocklistConfig{},
	)
	t.Cleanup(stop)
	return handler
}
