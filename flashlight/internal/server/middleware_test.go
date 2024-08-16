package server

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/stretchr/testify/assert"
)

type mockedRateLimiter struct {
	t           *testing.T
	allow       bool
	expectedKey string
}

func (m *mockedRateLimiter) Consume(key string) bool {
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
			expectedKey: "ip: 127.0.0.1",
		}
		ipRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
			rateLimiter, ratelimiting.IPKeyFunc,
		)

		w := httptest.NewRecorder()
		middleware := NewRateLimitMiddleware(ipRateLimiter)
		handler := middleware(
			func(w http.ResponseWriter, r *http.Request) {
				called = true
				w.WriteHeader(http.StatusOK)
			},
		)

		handler(w, &http.Request{RemoteAddr: "127.0.0.1"})

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

func TestComposeMiddlewares(t *testing.T) {
	t.Run("single middleware", func(t *testing.T) {
		handlerCalled := false
		middlewareStage := "not called"
		middleware := ComposeMiddlewares(
			func(next http.HandlerFunc) http.HandlerFunc {
				return func(w http.ResponseWriter, r *http.Request) {
					middlewareStage = "pre"
					next(w, r)
					middlewareStage = "post"
				}
			},
		)

		handler := middleware(
			func(w http.ResponseWriter, r *http.Request) {
				handlerCalled = true
				assert.Equal(t, "pre", middlewareStage)
			},
		)

		w := httptest.NewRecorder()
		handler(w, &http.Request{})

		assert.True(t, handlerCalled)
		assert.Equal(t, "post", middlewareStage)
	})

	t.Run("multiple middleware", func(t *testing.T) {
		handlerCalled := false

		stage1 := "not called"
		stage2 := "not called"
		stage3 := "not called"

		middleware1 := func(next http.HandlerFunc) http.HandlerFunc {
			return func(w http.ResponseWriter, r *http.Request) {
				assert.Equal(t, "not called", stage1)
				assert.Equal(t, "not called", stage2)
				assert.Equal(t, "not called", stage3)

				stage1 = "pre"
				next(w, r)
				stage1 = "post"

				assert.Equal(t, "post", stage1)
				assert.Equal(t, "post", stage2)
				assert.Equal(t, "post", stage3)
			}
		}
		middleware2 := func(next http.HandlerFunc) http.HandlerFunc {
			return func(w http.ResponseWriter, r *http.Request) {
				assert.Equal(t, "pre", stage1)
				assert.Equal(t, "not called", stage2)
				assert.Equal(t, "not called", stage3)

				stage2 = "pre"
				next(w, r)
				stage2 = "post"

				assert.Equal(t, "pre", stage1)
				assert.Equal(t, "post", stage2)
				assert.Equal(t, "post", stage3)
			}
		}
		middleware3 := func(next http.HandlerFunc) http.HandlerFunc {
			return func(w http.ResponseWriter, r *http.Request) {
				assert.Equal(t, "pre", stage1)
				assert.Equal(t, "pre", stage2)
				assert.Equal(t, "not called", stage3)

				stage3 = "pre"
				next(w, r)
				stage3 = "post"

				assert.Equal(t, "pre", stage1)
				assert.Equal(t, "pre", stage2)
				assert.Equal(t, "post", stage3)
			}
		}

		middleware := ComposeMiddlewares(middleware1, middleware2, middleware3)

		handler := middleware(
			func(w http.ResponseWriter, r *http.Request) {
				assert.Equal(t, "pre", stage1)
				assert.Equal(t, "pre", stage2)
				assert.Equal(t, "pre", stage3)
				handlerCalled = true
			},
		)

		w := httptest.NewRecorder()
		handler(w, &http.Request{})

		assert.True(t, handlerCalled)

		assert.Equal(t, "post", stage1)
		assert.Equal(t, "post", stage2)
		assert.Equal(t, "post", stage3)
	})
}
