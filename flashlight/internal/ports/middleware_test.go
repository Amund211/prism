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
	"sync"
	"testing"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
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
			expectedKey: fmt.Sprintf("ip: %s", HashIP("12.12.123.123")),
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

		registerUserVisit := func(ctx context.Context, userID string, ipHash string, userAgent string) (domain.User, error) {
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
			registerUserVisit := func(ctx context.Context, userID string, ipHash string, userAgent string) (domain.User, error) {
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

	t.Run("registerUserVisit gets called with low cardinality user ID from header", func(t *testing.T) {
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

		req := httptest.NewRequest(http.MethodGet, "/test", nil)
		req.Header.Set("X-User-Id", "test-user-123")
		w := httptest.NewRecorder()

		handler(w, req)

		wg.Wait()
		require.Equal(t, "<short-user-id>", registeredUserID)
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
		registerUserVisit := func(ctx context.Context, userID string, ipHash string, userAgent string) (domain.User, error) {
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

		req := httptest.NewRequest(http.MethodGet, "/test", nil)
		req.Header.Set("X-Forwarded-For", "12.12.123.123,34.111.7.239")
		w := httptest.NewRecorder()

		handler(w, req)

		wg.Wait()
		require.Equal(t, HashIP("12.12.123.123"), registeredIPHash)
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

		req := httptest.NewRequest(http.MethodGet, "/test", nil)
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
					HashIP("5.5.5.5"),
					HashIP("6.6.6.6"),
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
					HashIP("5.5.5.5"),
					HashIP("6.6.6.6"),
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

			req := httptest.NewRequest(http.MethodGet, "/test", nil)
			req.Header.Set("X-Forwarded-For", fmt.Sprintf("%s,34.111.7.239", tc.ip))
			require.Equal(t, tc.ip, GetIP(req), "XFF set incorrectly for IP")

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

	run := func(request *http.Request, useMiddleware bool) []StringAttr {
		t.Helper()

		buf := &bytes.Buffer{}
		middleware := NewRequestLoggerMiddleware(slog.New(slog.NewJSONHandler(buf, nil)))

		logRequest := func(w http.ResponseWriter, r *http.Request) {
			logging.FromContext(r.Context()).InfoContext(r.Context(), "test")
		}

		handler := logRequest
		if useMiddleware {
			handler = middleware(logRequest)
		}

		w := httptest.NewRecorder()
		handler(w, request)

		var logEntry map[string]interface{}
		err := json.Unmarshal(buf.Bytes(), &logEntry)
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

			requestUrl, err := url.Parse("http://example.com/my-path?uuid=requested-uuid")
			require.NoError(t, err)

			attrs := run(&http.Request{
				URL:    requestUrl,
				Method: "GET",
				Header: http.Header{
					"User-Agent": []string{"user-agent/1.0"},
					"X-User-Id":  []string{"this-is-a-long-enough-user-id"},
				},
			}, true)

			require.ElementsMatch(t, []StringAttr{
				{Key: "userAgent", Value: "user-agent/1.0"},
				{Key: "methodPath", Value: "GET /my-path"},
				{Key: "userId", Value: "this-is-a-long-enough-user-id"},
				{Key: "lowCardinalityUserId", Value: "this-is-a-long-enough-user-id"},
			}, attrs)
		})

		t.Run("short user id", func(t *testing.T) {
			t.Parallel()

			requestUrl, err := url.Parse("http://example.com/my-path")
			require.NoError(t, err)

			attrs := run(&http.Request{
				URL:    requestUrl,
				Method: "GET",
				Header: http.Header{
					"User-Agent": []string{"user-agent/1.0"},
					"X-User-Id":  []string{"short"},
				},
			}, true)

			require.ElementsMatch(t, []StringAttr{
				{Key: "userAgent", Value: "user-agent/1.0"},
				{Key: "methodPath", Value: "GET /my-path"},
				{Key: "userId", Value: "short"},
				{Key: "lowCardinalityUserId", Value: "<short-user-id>"},
			}, attrs)
		})

		t.Run("bad request", func(t *testing.T) {
			t.Parallel()

			requestUrl, err := url.Parse("http://example.com/my-other-path")
			require.NoError(t, err)

			attrs := run(&http.Request{
				URL:    requestUrl,
				Method: "POST",
			}, true)

			require.ElementsMatch(t, []StringAttr{
				{Key: "userAgent", Value: ""},
				{Key: "methodPath", Value: "POST /my-other-path"},
				{Key: "userId", Value: "<missing>"},
				{Key: "lowCardinalityUserId", Value: "<missing>"},
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

			req := httptest.NewRequest(http.MethodGet, "/test", nil)
			if tc.userIDHeader != "" {
				req.Header.Set("X-User-Id", tc.userIDHeader)
			}
			w := httptest.NewRecorder()

			handler(w, req)

			require.Equal(t, tc.expectedUserID, gotUserID)
		})
	}
}
