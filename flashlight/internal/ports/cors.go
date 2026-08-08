package ports

import (
	"fmt"
	"net/http"
	"strings"
)

type DomainSuffixes struct {
	suffixes []string
}

func NewDomainSuffixes(suffixes ...string) (*DomainSuffixes, error) {
	for _, suffix := range suffixes {
		if strings.HasPrefix(suffix, ".") {
			return nil, fmt.Errorf("domain suffix %s should not start with a dot", suffix)
		}
		if strings.Contains(suffix, "://") {
			return nil, fmt.Errorf("domain suffix %s should not contain a scheme", suffix)
		}
	}
	return &DomainSuffixes{
		suffixes: suffixes,
	}, nil
}

func (suffixes *DomainSuffixes) AnyMatch(origin string) bool {
	for _, suffix := range suffixes.suffixes {
		if originMatchesSuffix(origin, suffix) {
			return true
		}
	}
	return false
}

func originMatchesSuffix(origin string, suffix string) bool {
	// Literal match of the suffix (https://example.com)
	if origin == fmt.Sprintf("https://%s", suffix) {
		return true
	}

	// Only accept origins with https scheme
	if !strings.HasPrefix(origin, "https://") {
		return false
	}

	// Match any subdomain (https://*.example.com)
	if strings.HasSuffix(origin, fmt.Sprintf(".%s", suffix)) {
		return true
	}

	return false
}

func BuildCORSMiddleware(allowedSuffixes *DomainSuffixes) func(http.HandlerFunc) http.HandlerFunc {
	return func(next http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			origin := r.Header.Get("Origin")

			// The response depends on the request's Origin (it is echoed into
			// Access-Control-Allow-Origin, and its presence differs per origin),
			// so shared caches must key on it. Set unconditionally, including for
			// disallowed origins, to avoid a cached no-CORS response being served
			// to an allowed origin. Add (not Set) to preserve any downstream Vary.
			w.Header().Add("Vary", "Origin")

			if allowedSuffixes.AnyMatch(origin) {
				w.Header().Set("Access-Control-Allow-Origin", origin)

				if r.Method == http.MethodOptions {
					w.Header().Set("Access-Control-Allow-Methods", "GET,POST")
					w.Header().Set("Access-Control-Allow-Headers", "Content-Type, X-User-Id, X-Client-Type, X-Client-Version, Authorization")
					// TODO: Add longer max age (default 5s) when it works well
					// w.Header().Set("Access-Control-Max-Age", "3600")
					w.WriteHeader(http.StatusNoContent)
					return
				}

				// Without this a cross-origin caller cannot read the
				// header. Read off the response it appears on, not the
				// preflight.
				w.Header().Set("Access-Control-Expose-Headers", AuthRefreshHeader)
			}

			next(w, r)
		}
	}
}

func BuildCORSHandler(allowedSuffixes *DomainSuffixes) http.HandlerFunc {
	return BuildCORSMiddleware(allowedSuffixes)(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	})
}
