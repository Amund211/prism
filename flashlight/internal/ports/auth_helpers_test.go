package ports_test

import (
	"io"
	"log/slog"
	"net/http"
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
