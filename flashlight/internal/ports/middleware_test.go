package ports

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/stretchr/testify/assert"
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
			rateLimiter, IPKeyFunc,
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

func TestBuildRegisterUserVisitMiddleware(t *testing.T) {
	t.Parallel()

	makeHandler := func() (http.HandlerFunc, *bool) {
		called := false
		return func(w http.ResponseWriter, r *http.Request) {
			called = true
			w.WriteHeader(http.StatusOK)
		}, &called
	}

	t.Run("next handler gets called properly", func(t *testing.T) {
		t.Parallel()

		registerUserVisit := func(ctx context.Context, userID string) (domain.User, error) {
			return domain.User{}, nil
		}
		middleware := BuildRegisterUserVisitMiddleware(registerUserVisit)

		t.Run("with user ID header", func(t *testing.T) {
			inner, innerCalled := makeHandler()

			handler := middleware(inner)

			req := httptest.NewRequest(http.MethodGet, "/test", nil)
			req.Header.Set("X-User-Id", "test-user")
			w := httptest.NewRecorder()

			handler(w, req)

			require.True(t, *innerCalled)
			require.Equal(t, http.StatusOK, w.Code)
		})

		t.Run("without user ID header", func(t *testing.T) {
			inner, innerCalled := makeHandler()

			handler := middleware(inner)

			req := httptest.NewRequest(http.MethodGet, "/test", nil)
			w := httptest.NewRecorder()

			handler(w, req)

			require.True(t, *innerCalled)
			require.Equal(t, http.StatusOK, w.Code)
		})

		t.Run("with strange user ID header", func(t *testing.T) {
			inner, innerCalled := makeHandler()

			handler := middleware(inner)

			req := httptest.NewRequest(http.MethodGet, "/test", nil)
			req.Header.Set("X-User-Id", "test-user;`DROP TABLES;--      sdlfkjsdlkfj  ---; ^&^%$#@!")
			w := httptest.NewRecorder()

			handler(w, req)

			require.True(t, *innerCalled)
			require.Equal(t, http.StatusOK, w.Code)
		})

		t.Run("if registerUserVisit errors", func(t *testing.T) {
			registerUserVisit := func(ctx context.Context, userID string) (domain.User, error) {
				return domain.User{}, assert.AnError
			}
			middleware := BuildRegisterUserVisitMiddleware(registerUserVisit)

			inner, innerCalled := makeHandler()

			handler := middleware(inner)

			req := httptest.NewRequest(http.MethodGet, "/test", nil)
			req.Header.Set("X-User-Id", "test-user")
			w := httptest.NewRecorder()

			handler(w, req)

			require.True(t, *innerCalled)
			require.Equal(t, http.StatusOK, w.Code)
		})
	})

	t.Run("registerUserVisit gets called with user ID from header", func(t *testing.T) {
		t.Parallel()

		var wg sync.WaitGroup
		wg.Add(1)

		var registeredUserID string
		registerUserVisit := func(ctx context.Context, userID string) (domain.User, error) {
			defer wg.Done()
			registeredUserID = userID
			return domain.User{}, nil
		}
		middleware := BuildRegisterUserVisitMiddleware(registerUserVisit)

		inner, _ := makeHandler()
		handler := middleware(inner)

		req := httptest.NewRequest(http.MethodGet, "/test", nil)
		req.Header.Set("X-User-Id", "test-user-123")
		w := httptest.NewRecorder()

		handler(w, req)

		wg.Wait()
		require.Equal(t, "test-user-123", registeredUserID)
	})

	t.Run("registerUserVisit gets called with <missing> when no user ID header", func(t *testing.T) {
		t.Parallel()

		var wg sync.WaitGroup
		wg.Add(1)

		var registeredUserID string
		registerUserVisit := func(ctx context.Context, userID string) (domain.User, error) {
			defer wg.Done()
			registeredUserID = userID
			return domain.User{}, nil
		}
		middleware := BuildRegisterUserVisitMiddleware(registerUserVisit)

		inner, _ := makeHandler()
		handler := middleware(inner)

		req := httptest.NewRequest(http.MethodGet, "/test", nil)
		w := httptest.NewRecorder()

		handler(w, req)

		wg.Wait()
		require.Equal(t, "<missing>", registeredUserID)
	})

	t.Run("registerUserVisit gets called with <missing> when user ID header is empty string", func(t *testing.T) {
		t.Parallel()

		var wg sync.WaitGroup
		wg.Add(1)

		var registeredUserID string
		registerUserVisit := func(ctx context.Context, userID string) (domain.User, error) {
			defer wg.Done()
			registeredUserID = userID
			return domain.User{}, nil
		}
		middleware := BuildRegisterUserVisitMiddleware(registerUserVisit)

		inner, _ := makeHandler()
		handler := middleware(inner)

		req := httptest.NewRequest(http.MethodGet, "/test", nil)
		req.Header.Set("X-User-Id", "")
		w := httptest.NewRecorder()

		handler(w, req)

		wg.Wait()
		require.Equal(t, "<missing>", registeredUserID)
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
