package ports

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"net/url"
	"slices"
	"strings"
	"sync"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
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
			expectedKey: fmt.Sprintf("ip: %s", IP("12.12.123.123").Hash()),
		}
		ipRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
			rateLimiter, IPHashKeyFunc,
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

		req, err := http.NewRequestWithContext(t.Context(), "GET", "http://example.com/test", http.NoBody)
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

// keyForRequest returns the key UserIDKeyFunc produces for req, with the auth
// context attached the way production attaches it — by running the bearer
// middleware. session is what validation returns; nil means the request carries
// no Authorization header at all.
func keyForRequest(t *testing.T, req *http.Request, session *domain.AuthSession) string {
	t.Helper()

	validate := func(ctx context.Context, sessionID string) (domain.AuthSession, error) {
		require.NotNil(t, session, "validate should not be called without a bearer")
		return *session, nil
	}

	var key string
	reached := false
	handler := NewBearerAuthMiddleware(validate)(func(w http.ResponseWriter, r *http.Request) {
		reached = true
		key = UserIDKeyFunc(r)
	})

	if session != nil {
		req.Header.Set("Authorization", "Bearer flsess_good")
	}
	handler(httptest.NewRecorder(), req)

	require.True(t, reached, "the request should have reached the key func")
	return key
}

func TestUserIDKeyFunc(t *testing.T) {
	t.Parallel()

	anonymousSession := func(identityKey string) *domain.AuthSession {
		return &domain.AuthSession{
			ID:           "flsess_abc",
			IdentityType: domain.AuthSessionIdentityAnonymous,
			IdentityKey:  identityKey,
		}
	}

	makeRequest := func(t *testing.T, userIDHeader string) *http.Request {
		t.Helper()
		req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/playerdata", http.NoBody)
		if userIDHeader != "" {
			req.Header.Set("X-User-Id", userIDHeader)
		}
		return req
	}

	t.Run("falls back to the header without a bearer", func(t *testing.T) {
		t.Parallel()

		require.Equal(t,
			"user-id: this-is-a-long-enough-user-id",
			keyForRequest(t, makeRequest(t, "this-is-a-long-enough-user-id"), nil),
		)
	})

	t.Run("falls back to <missing> with neither", func(t *testing.T) {
		t.Parallel()

		require.Equal(t, "user-id: <missing>", keyForRequest(t, makeRequest(t, ""), nil))
	})

	t.Run("prefers the verified identity over the header", func(t *testing.T) {
		t.Parallel()

		require.Equal(t,
			"user-id: verified-identity-key",
			keyForRequest(t, makeRequest(t, "some-other-user-entirely"), anonymousSession("verified-identity-key")),
		)
	})

	t.Run("the anonymous tier shares the header's bucket", func(t *testing.T) {
		t.Parallel()

		// Not merely equal-looking: the same string, so the two land in the same
		// token bucket. A second key here would be a second budget, claimable by
		// dropping the Authorization header.
		userID := "the-very-same-user-id"
		require.Equal(t,
			keyForRequest(t, makeRequest(t, userID), nil),
			keyForRequest(t, makeRequest(t, ""), anonymousSession(userID)),
		)
	})

	t.Run("a long identity key truncates like the header does", func(t *testing.T) {
		t.Parallel()

		// Login accepts userIds up to 100 chars while the header stops at 50, so
		// without matching truncation this is where the two buckets diverge.
		longUserID := strings.Repeat("a", 80)
		require.Equal(t,
			keyForRequest(t, makeRequest(t, longUserID), nil),
			keyForRequest(t, makeRequest(t, ""), anonymousSession(longUserID)),
		)
		require.Equal(t, "user-id: "+strings.Repeat("a", 50), keyForRequest(t, makeRequest(t, ""), anonymousSession(longUserID)))
	})

	t.Run("an unknown tier gets its own namespace", func(t *testing.T) {
		t.Parallel()

		// A future tier's identity_key is a different kind of value (the
		// Microsoft tier's verified MC uuid), so it must not be reachable from
		// the self-asserted header.
		key := keyForRequest(t, makeRequest(t, ""), &domain.AuthSession{
			IdentityType: domain.AuthSessionIdentityType("microsoft"),
			IdentityKey:  "01234567-89ab-cdef-0123-456789abcdef",
		})

		require.Equal(t, "identity: microsoft: 01234567-89ab-cdef-0123-456789abcdef", key)
		require.NotEqual(t, key, keyForRequest(t, makeRequest(t, "01234567-89ab-cdef-0123-456789abcdef"), nil))
	})
}

// TestUserIDLimiterSpendsOneBudgetPerIdentity is the invariant task 2 leans on:
// authenticating must buy convenience, never throughput.
func TestUserIDLimiterSpendsOneBudgetPerIdentity(t *testing.T) {
	t.Parallel()

	const userID = "the-same-user-every-time"

	// No refill, so the two tokens in the bucket are all there will ever be.
	userIDLimiter, stop := ratelimiting.NewTokenBucketRateLimiter(
		ratelimiting.RefillPerSecond(0),
		ratelimiting.BurstSize(2),
	)
	t.Cleanup(stop)

	validate := func(ctx context.Context, sessionID string) (domain.AuthSession, error) {
		return domain.AuthSession{
			ID:           sessionID,
			IdentityType: domain.AuthSessionIdentityAnonymous,
			IdentityKey:  userID,
		}, nil
	}

	rateLimiter := ratelimiting.NewRequestBasedRateLimiter(userIDLimiter, UserIDKeyFunc)
	handler := ComposeMiddlewares(
		NewBearerAuthMiddleware(validate),
		NewRateLimitMiddleware(rateLimiter, func(w http.ResponseWriter, r *http.Request) {
			http.Error(w, "Rate limit exceeded", http.StatusTooManyRequests)
		}),
	)(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	send := func(t *testing.T, withBearer bool, headerUserID string) int {
		t.Helper()
		req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/playerdata", http.NoBody)
		if withBearer {
			req.Header.Set("Authorization", "Bearer flsess_good")
		}
		if headerUserID != "" {
			req.Header.Set("X-User-Id", headerUserID)
		}
		w := httptest.NewRecorder()
		handler(w, req)
		return w.Code
	}

	require.Equal(t, http.StatusOK, send(t, true, ""), "the bearer request should spend the first token")
	require.Equal(t, http.StatusOK, send(t, false, userID), "the header request should spend the second token from the same bucket")
	require.Equal(t, http.StatusTooManyRequests, send(t, true, ""),
		"dropping and re-adding the Authorization header must not buy a second budget")
	require.Equal(t, http.StatusOK, send(t, false, "somebody-else-entirely"),
		"a different identity should still have its own budget")
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

		registerUserVisit := func(ctx context.Context, userID string, ipHash string, userAgent string) (domain.User, error) {
			return domain.User{}, nil
		}
		middleware := BuildRegisterUserVisitMiddleware(registerUserVisit)

		t.Run("with user ID header", func(t *testing.T) {
			inner, innerCalled := makeHandler()

			handler := middleware(inner)

			req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
			req.Header.Set("X-User-Id", "test-user")
			w := httptest.NewRecorder()

			handler(w, req)

			require.True(t, *innerCalled)
			require.Equal(t, http.StatusOK, w.Code)
		})

		t.Run("without user ID header", func(t *testing.T) {
			inner, innerCalled := makeHandler()

			handler := middleware(inner)

			req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
			w := httptest.NewRecorder()

			handler(w, req)

			require.True(t, *innerCalled)
			require.Equal(t, http.StatusOK, w.Code)
		})

		t.Run("with strange user ID header", func(t *testing.T) {
			inner, innerCalled := makeHandler()

			handler := middleware(inner)

			req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
			req.Header.Set("X-User-Id", "test-user;`DROP TABLES;--      sdlfkjsdlkfj  ---; ^&^%$#@!")
			w := httptest.NewRecorder()

			handler(w, req)

			require.True(t, *innerCalled)
			require.Equal(t, http.StatusOK, w.Code)
		})

		t.Run("if registerUserVisit errors", func(t *testing.T) {
			registerUserVisit := func(ctx context.Context, userID string, ipHash string, userAgent string) (domain.User, error) {
				return domain.User{}, assert.AnError
			}
			middleware := BuildRegisterUserVisitMiddleware(registerUserVisit)

			inner, innerCalled := makeHandler()

			handler := middleware(inner)

			req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
			req.Header.Set("X-User-Id", "test-user")
			w := httptest.NewRecorder()

			handler(w, req)

			require.True(t, *innerCalled)
			require.Equal(t, http.StatusOK, w.Code)
		})
	})

	t.Run("registerUserVisit gets called with user ID from header, even if short", func(t *testing.T) {
		t.Parallel()

		var wg sync.WaitGroup
		wg.Add(1)

		var registeredUserID string
		registerUserVisit := func(ctx context.Context, userID string, ipHash string, userAgent string) (domain.User, error) {
			defer wg.Done()
			registeredUserID = userID
			return domain.User{}, nil
		}
		middleware := BuildRegisterUserVisitMiddleware(registerUserVisit)

		inner, _ := makeHandler()
		handler := middleware(inner)

		req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
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
		registerUserVisit := func(ctx context.Context, userID string, ipHash string, userAgent string) (domain.User, error) {
			defer wg.Done()
			registeredUserID = userID
			return domain.User{}, nil
		}
		middleware := BuildRegisterUserVisitMiddleware(registerUserVisit)

		inner, _ := makeHandler()
		handler := middleware(inner)

		req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
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
		registerUserVisit := func(ctx context.Context, userID string, ipHash string, userAgent string) (domain.User, error) {
			defer wg.Done()
			registeredUserID = userID
			return domain.User{}, nil
		}
		middleware := BuildRegisterUserVisitMiddleware(registerUserVisit)

		inner, _ := makeHandler()
		handler := middleware(inner)

		req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
		req.Header.Set("X-User-Id", "")
		w := httptest.NewRecorder()

		handler(w, req)

		wg.Wait()
		require.Equal(t, "<missing>", registeredUserID)
	})

	t.Run("registerUserVisit gets called with ip hash from request", func(t *testing.T) {
		t.Parallel()

		var wg sync.WaitGroup
		wg.Add(1)

		var registeredIPHash string
		registerUserVisit := func(ctx context.Context, userID string, ipHash string, userAgent string) (domain.User, error) {
			defer wg.Done()
			registeredIPHash = ipHash
			return domain.User{}, nil
		}
		middleware := BuildRegisterUserVisitMiddleware(registerUserVisit)

		inner, _ := makeHandler()
		handler := middleware(inner)

		req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
		req.Header.Set("X-Forwarded-For", "12.12.123.123,34.111.7.239")
		w := httptest.NewRecorder()

		handler(w, req)

		wg.Wait()
		require.Equal(t, IP("12.12.123.123").Hash(), registeredIPHash)
	})

	t.Run("registerUserVisit gets called with user agent from request", func(t *testing.T) {
		t.Parallel()

		var wg sync.WaitGroup
		wg.Add(1)

		var registeredUserAgent string
		registerUserVisit := func(ctx context.Context, userID string, ipHash string, userAgent string) (domain.User, error) {
			defer wg.Done()
			registeredUserAgent = userAgent
			return domain.User{}, nil
		}
		middleware := BuildRegisterUserVisitMiddleware(registerUserVisit)

		inner, _ := makeHandler()
		handler := middleware(inner)

		req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
		req.Header.Set("User-Agent", "TestBot/1.0")
		w := httptest.NewRecorder()

		handler(w, req)

		wg.Wait()
		require.Equal(t, "TestBot/1.0", registeredUserAgent)
	})
}

func TestBuildBlocklistMiddleware(t *testing.T) {
	t.Parallel()

	makeHandler := func() (http.HandlerFunc, *bool) {
		called := false
		return func(w http.ResponseWriter, r *http.Request) {
			called = true
			w.WriteHeader(http.StatusOK)
		}, &called
	}

	cases := []struct {
		name      string
		config    BlocklistConfig
		ip        string
		userAgent string
		userID    string
		blocked   bool
	}{
		{
			name:      "empty config",
			config:    BlocklistConfig{},
			ip:        "1.1.1.1",
			userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
			userID:    "user1",
			blocked:   false,
		},
		{
			name: "blocking different ips,uas,users",
			config: BlocklistConfig{
				IPs: []string{
					"1.2.2.2",
					"2.2.2.2",
					"3.2.2.2",
					"4.2.2.2",
				},
				UserAgents: []string{
					"BadBot/1.0",
					"EvilScraper/2.0",
				},
				UserIDs: []string{
					"bad-user-123",
					"evil-user-456",
				},
			},
			ip:        "1.1.1.1",
			userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
			userID:    "user1",
			blocked:   false,
		},
		{
			name: "blocked by ip",
			config: BlocklistConfig{
				IPs: []string{
					"1.2.2.2",
					"2.2.2.2",
					"3.2.2.2",
					"4.2.2.2",
				},
				UserAgents: []string{
					"BadBot/1.0",
					"EvilScraper/2.0",
				},
				UserIDs: []string{
					"bad-user-123",
					"evil-user-456",
				},
			},
			ip:        "1.2.2.2",
			userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
			userID:    "user1",
			blocked:   true,
		},
		{
			name: "blocked by user agent",
			config: BlocklistConfig{
				IPs: []string{
					"1.2.2.2",
					"2.2.2.2",
					"3.2.2.2",
					"4.2.2.2",
				},
				UserAgents: []string{
					"BadBot/1.0",
					"EvilScraper/2.0",
				},
				UserIDs: []string{
					"bad-user-123",
					"evil-user-456",
				},
			},
			ip:        "1.1.1.1",
			userAgent: "BadBot/1.0",
			userID:    "user1",
			blocked:   true,
		},
		{
			name: "blocked by user ID",
			config: BlocklistConfig{
				IPs: []string{
					"1.2.2.2",
					"2.2.2.2",
					"3.2.2.2",
					"4.2.2.2",
				},
				UserAgents: []string{
					"BadBot/1.0",
					"EvilScraper/2.0",
				},
				UserIDs: []string{
					"bad-user-123",
					"evil-user-456",
				},
			},
			ip:        "1.1.1.1",
			userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
			userID:    "bad-user-123",
			blocked:   true,
		},
		{
			name: "blocked by pre-hashed IP",
			config: BlocklistConfig{
				SHA256HexIPs: []string{
					IP("5.5.5.5").Hash(),
					IP("6.6.6.6").Hash(),
				},
			},
			ip:        "5.5.5.5",
			userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
			userID:    "user1",
			blocked:   true,
		},
		{
			name: "not blocked when pre-hashed IP doesn't match",
			config: BlocklistConfig{
				SHA256HexIPs: []string{
					IP("5.5.5.5").Hash(),
					IP("6.6.6.6").Hash(),
				},
			},
			ip:        "7.7.7.7",
			userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
			userID:    "user1",
			blocked:   false,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			middleware := BuildBlocklistMiddleware(tc.config)

			inner, innerCalled := makeHandler()

			handler := middleware(inner)

			req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
			req.Header.Set("X-Forwarded-For", fmt.Sprintf("%s,34.111.7.239", tc.ip))
			require.Equal(t, tc.ip, GetIP(req).String(), "XFF set incorrectly for IP")

			req.Header.Set("User-Agent", tc.userAgent)
			req.Header.Set("X-User-Id", tc.userID)
			w := httptest.NewRecorder()

			handler(w, req)

			if tc.blocked {
				require.False(t, *innerCalled)
				require.Equal(t, http.StatusBadRequest, w.Code)
			} else {
				require.True(t, *innerCalled)
				require.Equal(t, http.StatusOK, w.Code)
			}
		})
	}
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

type StringAttr struct {
	Key   string
	Value string
}

var ignoredAttrs = []string{"ip"}

func TestRequestLoggerMiddleware(t *testing.T) {
	t.Parallel()

	run := func(t *testing.T, request *http.Request) []StringAttr {
		t.Helper()

		buf := &bytes.Buffer{}
		middleware := NewRequestLoggerMiddleware(slog.New(slog.NewJSONHandler(buf, nil)))

		logRequest := func(w http.ResponseWriter, r *http.Request) {
			logging.FromContext(r.Context()).InfoContext(r.Context(), "test")
		}

		handler := middleware(logRequest)

		w := httptest.NewRecorder()
		handler(w, request)

		lines := bytes.Split(buf.Bytes(), []byte{'\n'})
		require.Len(t, lines, 5) // Normalizing client info + started + our log + done (+ last newline)

		var normalizedEntry map[string]interface{}
		err := json.Unmarshal(lines[0], &normalizedEntry)
		require.NoError(t, err)
		require.Equal(t, "Normalized client info", normalizedEntry["msg"])

		var startedEntry map[string]interface{}
		err = json.Unmarshal(lines[1], &startedEntry)
		require.NoError(t, err)
		require.Equal(t, "Handling request", startedEntry["msg"])

		var endedEntry map[string]interface{}
		err = json.Unmarshal(lines[3], &endedEntry)
		require.NoError(t, err)
		require.Equal(t, "Finished handling request", endedEntry["msg"])

		require.Empty(t, lines[4])

		var logEntry map[string]interface{}
		err = json.Unmarshal(lines[2], &logEntry)
		require.NoError(t, err)
		attrs := make([]StringAttr, 0)

		foundBase := 0
		for key, value := range logEntry {
			if key == "msg" {
				require.Equal(t, "test", value)
				foundBase++
			} else if key == "level" {
				require.Equal(t, "INFO", value)
				foundBase++
			} else if key == "time" {
				foundBase++
			} else if key == "correlationID" {
				foundBase++
			} else if key == "ipHash" {
				foundBase++
			} else if slices.Contains(ignoredAttrs, key) {
				continue
			} else {
				attrs = append(attrs, StringAttr{Key: key, Value: value.(string)})
			}
		}

		require.Equal(t, 5, foundBase)

		return attrs
	}

	t.Run("with middleware", func(t *testing.T) {
		t.Parallel()

		t.Run("all props", func(t *testing.T) {
			t.Parallel()

			requestURL, err := url.Parse("http://example.com/my-path?uuid=requested-uuid")
			require.NoError(t, err)

			attrs := run(t, &http.Request{
				URL:    requestURL,
				Method: "GET",
				Header: http.Header{
					"User-Agent": []string{"user-agent/1.0"},
					"X-User-Id":  []string{"this-is-a-long-enough-user-id"},
				},
			})

			require.ElementsMatch(t, []StringAttr{
				{Key: "userAgent", Value: "user-agent/1.0"},
				{Key: "methodPath", Value: "GET /my-path"},
				{Key: "userId", Value: "this-is-a-long-enough-user-id"},
				{Key: "lowCardinalityUserId", Value: "this-is-a-long-enough-user-id"},
				{Key: "clientType", Value: "missing"},
				{Key: "clientVersion", Value: "missing"},
			}, attrs)
		})

		t.Run("short user id", func(t *testing.T) {
			t.Parallel()

			requestURL, err := url.Parse("http://example.com/my-path")
			require.NoError(t, err)

			attrs := run(t, &http.Request{
				URL:    requestURL,
				Method: "GET",
				Header: http.Header{
					"User-Agent": []string{"user-agent/1.0"},
					"X-User-Id":  []string{"short"},
				},
			})

			require.ElementsMatch(t, []StringAttr{
				{Key: "userAgent", Value: "user-agent/1.0"},
				{Key: "methodPath", Value: "GET /my-path"},
				{Key: "userId", Value: "short"},
				{Key: "lowCardinalityUserId", Value: "<short-user-id>"},
				{Key: "clientType", Value: "missing"},
				{Key: "clientVersion", Value: "missing"},
			}, attrs)
		})

		t.Run("bad request", func(t *testing.T) {
			t.Parallel()

			requestURL, err := url.Parse("http://example.com/my-other-path")
			require.NoError(t, err)

			attrs := run(t, &http.Request{
				URL:    requestURL,
				Method: "POST",
			})

			require.ElementsMatch(t, []StringAttr{
				{Key: "userAgent", Value: ""},
				{Key: "methodPath", Value: "POST /my-other-path"},
				{Key: "userId", Value: "<missing>"},
				{Key: "lowCardinalityUserId", Value: "<missing>"},
				{Key: "clientType", Value: "missing"},
				{Key: "clientVersion", Value: "missing"},
			}, attrs)
		})

		t.Run("with client headers", func(t *testing.T) {
			t.Parallel()

			requestURL, err := url.Parse("http://example.com/my-path")
			require.NoError(t, err)

			attrs := run(t, &http.Request{
				URL:    requestURL,
				Method: "GET",
				Header: http.Header{
					"X-Client-Type":    []string{"prism"},
					"X-Client-Version": []string{"v1.12.0"},
				},
			})

			require.ElementsMatch(t, []StringAttr{
				{Key: "userAgent", Value: ""},
				{Key: "methodPath", Value: "GET /my-path"},
				{Key: "userId", Value: "<missing>"},
				{Key: "lowCardinalityUserId", Value: "<missing>"},
				{Key: "clientType", Value: "prism"},
				{Key: "clientVersion", Value: "v1.12.0"},
			}, attrs)
		})
	})

	t.Run("without middleware", func(t *testing.T) {
		t.Parallel()

		logging.FromContext(t.Context()).InfoContext(t.Context(), "don't crash when no logger in context")
	})
}

func TestNewReportingMetaMiddleware(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name           string
		userIDHeader   string
		expectedUserID string
	}{
		{
			name:           "with user ID header",
			userIDHeader:   "this-is-a-long-enough-user-id",
			expectedUserID: "this-is-a-long-enough-user-id",
		},
		{
			name:           "without user ID header",
			userIDHeader:   "",
			expectedUserID: "<missing>",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			middleware := NewReportingMetaMiddleware("test-port")

			var gotUserID string
			handler := middleware(func(w http.ResponseWriter, r *http.Request) {
				gotUserID = reporting.GetUserIDFromContext(r.Context())
				w.WriteHeader(http.StatusOK)
			})

			req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
			if tc.userIDHeader != "" {
				req.Header.Set("X-User-Id", tc.userIDHeader)
			}
			w := httptest.NewRecorder()

			handler(w, req)

			require.Equal(t, tc.expectedUserID, gotUserID)
		})
	}
}
