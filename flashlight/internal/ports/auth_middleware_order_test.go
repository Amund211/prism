package ports_test

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/ports"
)

// The nine handlers below mount the bearer auth middleware, each assembling
// its own chain by hand. They all have to mount it in the same slot: behind
// the blocklist and the IP limiters, inside CORS, and ahead of the user-id
// limiter. See NewBearerAuthMiddleware for why. Nothing but this test keeps
// the nine in agreement — both arrangements serve correct responses, one just
// does it without a throttle in front.

// The bearer probe rejects every request, so it short-circuits ahead of the
// handler bodies and these are never called. They exist to satisfy the
// constructors.
func unusedRegisterUserVisit(context.Context, string, string, string) (domain.User, error) {
	return domain.User{}, nil
}

func unusedGetAndPersistPlayerWithCache(context.Context, string, app.ProviderMode, string) (*domain.PlayerPIT, error) {
	return nil, nil
}

func unusedGetTags(context.Context, string, *string) (domain.Tags, error) {
	return domain.Tags{}, nil
}

func unusedGetPrismNotices(context.Context, string, string, app.UpdateSelection) []app.PrismNotice {
	return nil
}

func unusedGetHistory(context.Context, string, time.Time, time.Time, int) ([]domain.PlayerPIT, error) {
	return nil, nil
}

func unusedGetPlayerPITs(context.Context, string, time.Time, time.Time) ([]domain.PlayerPIT, error) {
	return nil, nil
}

func unusedComputeSessions(context.Context, []domain.PlayerPIT, time.Time, time.Time) []domain.Session {
	return nil
}

func unusedGetSessionAt(context.Context, string, time.Time) (app.SessionAtResult, error) {
	return app.SessionAtResult{}, nil
}

func unusedGetAccountByUsername(context.Context, string) (domain.Account, error) {
	return domain.Account{}, nil
}

func unusedGetAccountByUUID(context.Context, string) (domain.Account, error) {
	return domain.Account{}, nil
}

type bearerMountCase struct {
	name string
	path string
	// hasCORS marks the browser-facing handlers, where a 401 from the bearer
	// middleware has to carry Access-Control-Allow-Origin.
	hasCORS bool
	// aboveUserIDBurst is a request count larger than this handler's user-id
	// burst but smaller than its smallest IP burst.
	aboveUserIDBurst int
	build            func(t *testing.T, bearerAuthMiddleware func(http.HandlerFunc) http.HandlerFunc, blocklistConfig ports.BlocklistConfig) http.HandlerFunc
}

func bearerMountCases(t *testing.T) []bearerMountCase {
	t.Helper()

	allowedOrigins := authTestOrigins(t)

	return []bearerMountCase{
		{
			name:             "playerdata",
			aboveUserIDBurst: 150,
			path:             "/v1/playerdata",
			build: func(t *testing.T, bearerAuthMiddleware func(http.HandlerFunc) http.HandlerFunc, blocklistConfig ports.BlocklistConfig) http.HandlerFunc {
				handler, stop := ports.MakeGetPlayerDataHandler(
					unusedGetAndPersistPlayerWithCache,
					unusedRegisterUserVisit,
					authTestLogger,
					noopAuthMiddleware,
					bearerAuthMiddleware,
					blocklistConfig,
					false,
				)
				t.Cleanup(stop)
				return handler
			},
		},
		{
			name:             "tags",
			aboveUserIDBurst: 150,
			path:             "/v1/tags/01234567-89ab-cdef-0123-456789abcdef",
			build: func(t *testing.T, bearerAuthMiddleware func(http.HandlerFunc) http.HandlerFunc, blocklistConfig ports.BlocklistConfig) http.HandlerFunc {
				handler, stop := ports.MakeGetTagsHandler(
					unusedGetTags,
					unusedRegisterUserVisit,
					authTestLogger,
					noopAuthMiddleware,
					bearerAuthMiddleware,
					blocklistConfig,
				)
				t.Cleanup(stop)
				return handler
			},
		},
		{
			name:             "prism-notices",
			aboveUserIDBurst: 150,
			path:             "/v1/prism-notices",
			build: func(t *testing.T, bearerAuthMiddleware func(http.HandlerFunc) http.HandlerFunc, blocklistConfig ports.BlocklistConfig) http.HandlerFunc {
				handler, stop := ports.MakePrismNoticesHandler(
					unusedGetPrismNotices,
					unusedRegisterUserVisit,
					authTestLogger,
					noopAuthMiddleware,
					bearerAuthMiddleware,
					blocklistConfig,
				)
				t.Cleanup(stop)
				return handler
			},
		},
		{
			name:             "history",
			aboveUserIDBurst: 100,
			path:             "/v1/history",
			hasCORS:          true,
			build: func(t *testing.T, bearerAuthMiddleware func(http.HandlerFunc) http.HandlerFunc, blocklistConfig ports.BlocklistConfig) http.HandlerFunc {
				handler, stop := ports.MakeGetHistoryHandler(
					unusedGetHistory,
					unusedRegisterUserVisit,
					allowedOrigins,
					authTestLogger,
					noopAuthMiddleware,
					bearerAuthMiddleware,
					blocklistConfig,
				)
				t.Cleanup(stop)
				return handler
			},
		},
		{
			name:             "sessions",
			aboveUserIDBurst: 50,
			path:             "/v1/sessions",
			hasCORS:          true,
			build: func(t *testing.T, bearerAuthMiddleware func(http.HandlerFunc) http.HandlerFunc, blocklistConfig ports.BlocklistConfig) http.HandlerFunc {
				handler, stop := ports.MakeGetSessionsHandler(
					unusedGetPlayerPITs,
					unusedComputeSessions,
					unusedRegisterUserVisit,
					allowedOrigins,
					authTestLogger,
					noopAuthMiddleware,
					bearerAuthMiddleware,
					blocklistConfig,
				)
				t.Cleanup(stop)
				return handler
			},
		},
		{
			name:             "session-at",
			aboveUserIDBurst: 50,
			path:             "/v1/session-at",
			hasCORS:          true,
			build: func(t *testing.T, bearerAuthMiddleware func(http.HandlerFunc) http.HandlerFunc, blocklistConfig ports.BlocklistConfig) http.HandlerFunc {
				handler, stop := ports.MakeGetSessionAtHandler(
					unusedGetSessionAt,
					unusedRegisterUserVisit,
					allowedOrigins,
					authTestLogger,
					noopAuthMiddleware,
					bearerAuthMiddleware,
					blocklistConfig,
				)
				t.Cleanup(stop)
				return handler
			},
		},
		{
			name:             "wrapped",
			aboveUserIDBurst: 100,
			path:             "/v1/wrapped/01234567-89ab-cdef-0123-456789abcdef/2024",
			hasCORS:          true,
			build: func(t *testing.T, bearerAuthMiddleware func(http.HandlerFunc) http.HandlerFunc, blocklistConfig ports.BlocklistConfig) http.HandlerFunc {
				handler, stop := ports.MakeGetWrappedHandler(
					unusedGetPlayerPITs,
					unusedComputeSessions,
					unusedRegisterUserVisit,
					allowedOrigins,
					authTestLogger,
					noopAuthMiddleware,
					bearerAuthMiddleware,
					blocklistConfig,
				)
				t.Cleanup(stop)
				return handler
			},
		},
		{
			name:             "get_account_by_username",
			aboveUserIDBurst: 150,
			path:             "/v1/accounts/username/Player",
			hasCORS:          true,
			build: func(t *testing.T, bearerAuthMiddleware func(http.HandlerFunc) http.HandlerFunc, blocklistConfig ports.BlocklistConfig) http.HandlerFunc {
				handler, stop := ports.MakeGetAccountByUsernameHandler(
					unusedGetAccountByUsername,
					unusedRegisterUserVisit,
					allowedOrigins,
					authTestLogger,
					noopAuthMiddleware,
					bearerAuthMiddleware,
					blocklistConfig,
				)
				t.Cleanup(stop)
				return handler
			},
		},
		{
			name:             "get_account_by_uuid",
			aboveUserIDBurst: 150,
			path:             "/v1/accounts/uuid/01234567-89ab-cdef-0123-456789abcdef",
			hasCORS:          true,
			build: func(t *testing.T, bearerAuthMiddleware func(http.HandlerFunc) http.HandlerFunc, blocklistConfig ports.BlocklistConfig) http.HandlerFunc {
				handler, stop := ports.MakeGetAccountByUUIDHandler(
					unusedGetAccountByUUID,
					unusedRegisterUserVisit,
					allowedOrigins,
					authTestLogger,
					noopAuthMiddleware,
					bearerAuthMiddleware,
					blocklistConfig,
				)
				t.Cleanup(stop)
				return handler
			},
		},
	}
}

func TestBearerAuthMiddlewareMountPosition(t *testing.T) {
	t.Parallel()

	// A bad token is the interesting case: it is what an attacker sends, and
	// it is the arm that must stay behind the limiters and inside CORS.
	makeCountingBearerMiddleware := func(calls *int) func(http.HandlerFunc) http.HandlerFunc {
		return func(http.HandlerFunc) http.HandlerFunc {
			return func(w http.ResponseWriter, r *http.Request) {
				*calls++
				http.Error(w, "Invalid or expired session", http.StatusUnauthorized)
			}
		}
	}

	for _, tc := range bearerMountCases(t) {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			makeRequest := func(t *testing.T, ip string, userID string) *http.Request {
				t.Helper()
				req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, tc.path, http.NoBody)
				withRequestIP(req, ip)
				req.Header.Set("Authorization", "Bearer flsess_garbage")
				if userID != "" {
					req.Header.Set("X-User-Id", userID)
				}
				return req
			}

			t.Run("an ordinary request reaches the bearer middleware", func(t *testing.T) {
				t.Parallel()

				calls := 0
				handler := tc.build(t, makeCountingBearerMiddleware(&calls), emptyBlocklistConfig)

				origin := "https://subdomain.example.com"
				req := makeRequest(t, "203.0.113.1", "")
				req.Header.Set("Origin", origin)
				w := httptest.NewRecorder()

				handler.ServeHTTP(w, req)

				require.Equal(t, http.StatusUnauthorized, w.Code)
				require.Equal(t, 1, calls)

				if tc.hasCORS {
					require.Equal(t, origin, w.Header().Get("Access-Control-Allow-Origin"),
						"the bearer middleware must sit inside CORS, or the browser can't read the 401 and reports an opaque network error")
				}
			})

			t.Run("blocked requests don't reach the bearer middleware", func(t *testing.T) {
				t.Parallel()

				blockedIP := "203.0.113.2"
				calls := 0
				handler := tc.build(
					t,
					makeCountingBearerMiddleware(&calls),
					ports.BlocklistConfig{IPs: []string{blockedIP}},
				)

				w := httptest.NewRecorder()
				handler.ServeHTTP(w, makeRequest(t, blockedIP, ""))

				require.Equal(t, http.StatusBadRequest, w.Code)
				require.Zero(t, calls, "a blocklisted caller must not be able to spend DB work on bearer validation")
			})

			t.Run("the user-id limiter sits behind the bearer middleware", func(t *testing.T) {
				t.Parallel()

				calls := 0
				handler := tc.build(t, makeCountingBearerMiddleware(&calls), emptyBlocklistConfig)

				// Same caller every time, well past the user-id burst. That
				// limiter is behind the bearer middleware — so it never gets to
				// spend a token — which is what will let it key on the verified
				// identity instead of the self-asserted X-User-Id header.
				for range tc.aboveUserIDBurst {
					w := httptest.NewRecorder()
					handler.ServeHTTP(w, makeRequest(t, "203.0.113.4", "the-same-user-every-time"))
					require.Equal(t, http.StatusUnauthorized, w.Code)
				}

				require.Equal(t, tc.aboveUserIDBurst, calls)
			})

			t.Run("throttled requests don't reach the bearer middleware", func(t *testing.T) {
				t.Parallel()

				calls := 0
				handler := tc.build(t, makeCountingBearerMiddleware(&calls), emptyBlocklistConfig)

				// Every request carries a fresh X-User-Id, so the per-user
				// bucket never runs dry and the limiter that eventually bites
				// is necessarily an IP one. That's the one that has to be in
				// front: the user-id limiter is deliberately behind the bearer
				// middleware so it can key on the verified identity.
				reachedBearer := 0
				var lastCode int
				for i := range 700 {
					w := httptest.NewRecorder()
					handler.ServeHTTP(w, makeRequest(t, "203.0.113.3", fmt.Sprintf("user-%d", i)))
					lastCode = w.Code
					if lastCode != http.StatusUnauthorized {
						break
					}
					reachedBearer++
				}

				require.Equal(t, http.StatusTooManyRequests, lastCode, "the IP limiter should bite within the burst we send")
				require.Positive(t, reachedBearer, "the burst should reach the bearer middleware")
				require.Equal(t, reachedBearer, calls, "the throttled request must not reach the bearer middleware")
			})
		})
	}
}
