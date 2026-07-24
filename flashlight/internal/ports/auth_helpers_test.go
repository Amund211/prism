package ports_test

import (
	"io"
	"log/slog"
	"net/http"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/ports"
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
