package ports

import (
	"net/http"
	"testing"
)

func TestNormalizeMethod(t *testing.T) {
	cases := map[string]string{
		http.MethodGet:     "GET",
		http.MethodPost:    "POST",
		http.MethodHead:    "HEAD",
		http.MethodOptions: "OPTIONS",
		http.MethodDelete:  "DELETE",
		// Non-standard / attacker-controlled tokens collapse to "other".
		"FOOBAR":     "other",
		"get":        "other", // methods are case-sensitive
		"":           "other",
		"GET /admin": "other",
	}

	for method, want := range cases {
		if got := normalizeMethod(method); got != want {
			t.Errorf("normalizeMethod(%q) = %q, want %q", method, got, want)
		}
	}
}
