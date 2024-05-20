package server

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
)

type mockedRateLimiter struct {
	t           *testing.T
	allow       bool
	expectedKey string
}

func (m *mockedRateLimiter) Allow(key string) bool {
	assert.Equal(m.t, m.expectedKey, key)
	return m.allow
}

func TestRateLimitMiddleware(t *testing.T) {
	runTest := func(t *testing.T, allow bool) {
		t.Helper()
		called := false
		rateLimiter := &mockedRateLimiter{
			t:           t,
			allow:       allow,
			expectedKey: "user1",
		}

		w := httptest.NewRecorder()
		middleware := NewRateLimitMiddleware(rateLimiter)
		handler := middleware(
			func(w http.ResponseWriter, r *http.Request) {
				called = true
				w.WriteHeader(http.StatusOK)
			},
		)

		handler(w, &http.Request{RemoteAddr: "user1"})

		if allow {
			assert.True(t, called, "Expected handler to be called")
			assert.Equal(t, http.StatusOK, w.Code)
		} else {
			assert.False(t, called, "Expected handler to not be called")
			assert.Equal(t, http.StatusTooManyRequests, w.Code)
		}
	}

	t.Run("allowed", func(t *testing.T) {
		runTest(t, true)
	})

	t.Run("not allowed", func(t *testing.T) {
		runTest(t, false)
	})
}
