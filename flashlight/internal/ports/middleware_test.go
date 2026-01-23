package ports

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/stretchr/testify/require"
)

type mockedRateLimiter struct {
	t           *testing.T
	allow       bool
	expectedKey string
}

func (m *mockedRateLimiter) Consume(key string) bool {
	m.t.Helper()
	require.Equal(m.t, m.expectedKey, key)
	return m.allow
}

func TestRateLimitMiddleware(t *testing.T) {
	t.Parallel()

	runTest := func(t *testing.T, allow bool) {
		t.Helper()
		handlerCalled := false
		onLimitExceededCalled := false
		rateLimiter := &mockedRateLimiter{
			t:           t,
			allow:       allow,
			expectedKey: "ip: 12.12.123.123",
		}
		ipRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
			rateLimiter, ratelimiting.IPKeyFunc,
		)

		w := httptest.NewRecorder()
		middleware := NewRateLimitMiddleware(
			ipRateLimiter,
			func(w http.ResponseWriter, r *http.Request) {
				onLimitExceededCalled = true
				http.Error(w, "Rate limit exceeded", http.StatusTooManyRequests)
			},
		)
		handler := middleware(
			func(w http.ResponseWriter, r *http.Request) {
				handlerCalled = true
				w.WriteHeader(http.StatusOK)
			},
		)

		req, err := http.NewRequest("GET", "http://example.com/test", nil)
		require.NoError(t, err)
		req.RemoteAddr = "169.254.169.126:58418"
		req.Header.Set("X-Forwarded-For", "12.12.123.123,34.111.7.239")

		handler(w, req)

		if allow {
			require.True(t, handlerCalled, "Expected handler to be called")
			require.False(t, onLimitExceededCalled)
			require.Equal(t, http.StatusOK, w.Code)
		} else {
			require.True(t, onLimitExceededCalled)
			require.False(t, handlerCalled, "Expected handler to not be called")
			require.Equal(t, http.StatusTooManyRequests, w.Code)
		}
	}

	t.Run("allowed", func(t *testing.T) {
		t.Parallel()

		runTest(t, true)
	})

	t.Run("not allowed", func(t *testing.T) {
		t.Parallel()

		runTest(t, false)
	})
}

func TestComposeMiddlewares(t *testing.T) {
	t.Parallel()

	t.Run("single middleware", func(t *testing.T) {
		t.Parallel()

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
				require.Equal(t, "pre", middlewareStage)
			},
		)

		w := httptest.NewRecorder()
		handler(w, &http.Request{})

		require.True(t, handlerCalled)
		require.Equal(t, "post", middlewareStage)
	})

	t.Run("multiple middleware", func(t *testing.T) {
		t.Parallel()

		handlerCalled := false

		stage1 := "not called"
		stage2 := "not called"
		stage3 := "not called"

		middleware1 := func(next http.HandlerFunc) http.HandlerFunc {
			return func(w http.ResponseWriter, r *http.Request) {
				require.Equal(t, "not called", stage1)
				require.Equal(t, "not called", stage2)
				require.Equal(t, "not called", stage3)

				stage1 = "pre"
				next(w, r)
				stage1 = "post"

				require.Equal(t, "post", stage1)
				require.Equal(t, "post", stage2)
				require.Equal(t, "post", stage3)
			}
		}
		middleware2 := func(next http.HandlerFunc) http.HandlerFunc {
			return func(w http.ResponseWriter, r *http.Request) {
				require.Equal(t, "pre", stage1)
				require.Equal(t, "not called", stage2)
				require.Equal(t, "not called", stage3)

				stage2 = "pre"
				next(w, r)
				stage2 = "post"

				require.Equal(t, "pre", stage1)
				require.Equal(t, "post", stage2)
				require.Equal(t, "post", stage3)
			}
		}
		middleware3 := func(next http.HandlerFunc) http.HandlerFunc {
			return func(w http.ResponseWriter, r *http.Request) {
				require.Equal(t, "pre", stage1)
				require.Equal(t, "pre", stage2)
				require.Equal(t, "not called", stage3)

				stage3 = "pre"
				next(w, r)
				stage3 = "post"

				require.Equal(t, "pre", stage1)
				require.Equal(t, "pre", stage2)
				require.Equal(t, "post", stage3)
			}
		}

		middleware := ComposeMiddlewares(middleware1, middleware2, middleware3)

		handler := middleware(
			func(w http.ResponseWriter, r *http.Request) {
				require.Equal(t, "pre", stage1)
				require.Equal(t, "pre", stage2)
				require.Equal(t, "pre", stage3)
				handlerCalled = true
			},
		)

		w := httptest.NewRecorder()
		handler(w, &http.Request{})

		require.True(t, handlerCalled)

		require.Equal(t, "post", stage1)
		require.Equal(t, "post", stage2)
		require.Equal(t, "post", stage3)
	})
}
