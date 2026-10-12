package ports_test

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/ports"
	"github.com/Amund211/flashlight/internal/ratelimiting"
)

// Bearer tokens of the form "<tier>:<identity key>" validate to that session.
func tierValidate(ctx context.Context, sessionID string) (domain.AuthSession, error) {
	tier, key, ok := strings.Cut(sessionID, ":")
	if !ok {
		return domain.AuthSession{}, errors.New("bad test token")
	}
	return domain.AuthSession{
		ID:           sessionID,
		IdentityType: domain.AuthSessionIdentityType(tier),
		IdentityKey:  key,
		ExpiresAt:    time.Now().Add(time.Hour),
	}, nil
}

type tierRequest struct {
	ip     string
	userID string
	bearer string
}

func newTierHandler(t *testing.T, policy ports.RateLimitPolicy) func(tierRequest) int {
	t.Helper()
	rateLimit, stop := ports.NewAuthRateLimitMiddleware(policy, func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "Rate limit exceeded", http.StatusTooManyRequests)
	})
	t.Cleanup(stop)

	handler := ports.ComposeMiddlewares(
		ports.NewBearerAuthMiddleware(tierValidate, time.Now, ports.BlocklistConfig{}),
		rateLimit,
	)(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	return func(tr tierRequest) int {
		req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/playerdata", http.NoBody)
		req.Header.Set("X-Forwarded-For", tr.ip+",34.111.7.239")
		if tr.userID != "" {
			req.Header.Set("X-User-Id", tr.userID)
		}
		if tr.bearer != "" {
			req.Header.Set("Authorization", "Bearer "+tr.bearer)
		}
		w := httptest.NewRecorder()
		handler(w, req)
		return w.Code
	}
}

// No refill anywhere, so a burst is all a bucket will ever hold.
func burst(n int) ports.Rate {
	return ports.Rate{Refill: 0, Burst: ratelimiting.BurstSize(n)}
}

func TestAuthRateLimitMiddleware(t *testing.T) {
	t.Parallel()

	const (
		ip1   = "12.12.123.123"
		ip2   = "13.13.123.123"
		user1 = "this-is-a-long-enough-user-id"
		user2 = "this-is-another-long-user-id"
	)

	t.Run("panics without the bearer middleware in front", func(t *testing.T) {
		t.Parallel()
		rateLimit, stop := ports.NewAuthRateLimitMiddleware(ports.RateLimitPolicy{
			UnauthedIP: burst(10),
			Identity:   map[ports.Tier]ports.Rate{ports.TierAnonymous: burst(10)},
		}, func(w http.ResponseWriter, r *http.Request) {})
		t.Cleanup(stop)
		handler := rateLimit(func(w http.ResponseWriter, r *http.Request) {})

		req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/v1/playerdata", http.NoBody)
		require.Panics(t, func() { handler(httptest.NewRecorder(), req) })
	})

	t.Run("panics at construction without an anonymous rate", func(t *testing.T) {
		t.Parallel()
		require.Panics(t, func() {
			ports.NewAuthRateLimitMiddleware(ports.RateLimitPolicy{
				UnauthedIP: burst(10),
				Identity:   map[ports.Tier]ports.Rate{ports.TierNone: burst(10)},
			}, func(w http.ResponseWriter, r *http.Request) {})
		})
	})

	t.Run("limits tier none per identity", func(t *testing.T) {
		t.Parallel()
		send := newTierHandler(t, ports.RateLimitPolicy{
			UnauthedIP: burst(10),
			Identity: map[ports.Tier]ports.Rate{
				ports.TierAnonymous: burst(10),
				ports.TierNone:      burst(2),
			},
		})
		require.Equal(t, http.StatusOK, send(tierRequest{ip: ip1, userID: user1}))
		require.Equal(t, http.StatusOK, send(tierRequest{ip: ip1, userID: user1}))
		require.Equal(t, http.StatusTooManyRequests, send(tierRequest{ip: ip1, userID: user1}))
		require.Equal(t, http.StatusOK, send(tierRequest{ip: ip1, userID: user2}), "another identity has its own budget")
	})

	t.Run("none and anonymous share one IP bucket", func(t *testing.T) {
		t.Parallel()
		send := newTierHandler(t, ports.RateLimitPolicy{
			UnauthedIP: burst(2),
			Identity:   map[ports.Tier]ports.Rate{ports.TierAnonymous: burst(10), ports.TierNone: burst(10)},
		})
		require.Equal(t, http.StatusOK, send(tierRequest{ip: ip1, userID: user1}))
		require.Equal(t, http.StatusOK, send(tierRequest{ip: ip1, bearer: "anonymous:" + user1}))
		require.Equal(t, http.StatusTooManyRequests, send(tierRequest{ip: ip1, userID: user2}),
			"switching tier must not buy a second IP budget")
		require.Equal(t, http.StatusTooManyRequests, send(tierRequest{ip: ip1, bearer: "anonymous:" + user2}))
		require.Equal(t, http.StatusOK, send(tierRequest{ip: ip2, userID: user1}), "another IP has its own budget")
	})

	t.Run("microsoft skips the IP bucket", func(t *testing.T) {
		t.Parallel()
		send := newTierHandler(t, ports.RateLimitPolicy{
			UnauthedIP: burst(1),
			Identity: map[ports.Tier]ports.Rate{
				ports.TierAnonymous: burst(10),
				ports.TierMicrosoft: burst(3),
			},
		})
		require.Equal(t, http.StatusOK, send(tierRequest{ip: ip1, userID: user1}), "spends the only IP token")
		for range 3 {
			require.Equal(t, http.StatusOK, send(tierRequest{ip: ip1, bearer: "microsoft:" + user1}))
		}
		require.Equal(t, http.StatusTooManyRequests, send(tierRequest{ip: ip2, bearer: "microsoft:" + user1}),
			"the identity budget holds across IPs")
	})

	t.Run("the identity key includes the tier", func(t *testing.T) {
		t.Parallel()
		send := newTierHandler(t, ports.RateLimitPolicy{
			UnauthedIP: burst(10),
			Identity:   map[ports.Tier]ports.Rate{ports.TierAnonymous: burst(1), ports.TierNone: burst(1)},
		})
		require.Equal(t, http.StatusOK, send(tierRequest{ip: ip1, bearer: "anonymous:" + user1}))
		require.Equal(t, http.StatusOK, send(tierRequest{ip: ip1, userID: user1}),
			"an unauthed header must not drain the anonymous user's bucket")
		require.Equal(t, http.StatusTooManyRequests, send(tierRequest{ip: ip1, bearer: "anonymous:" + user1}))
		require.Equal(t, http.StatusTooManyRequests, send(tierRequest{ip: ip1, userID: user1}))
	})

	t.Run("a tier missing from the policy uses the anonymous rate", func(t *testing.T) {
		t.Parallel()
		send := newTierHandler(t, ports.RateLimitPolicy{
			UnauthedIP: burst(10),
			Identity:   map[ports.Tier]ports.Rate{ports.TierAnonymous: burst(1)},
		})
		require.Equal(t, http.StatusOK, send(tierRequest{ip: ip1, userID: user1}))
		require.Equal(t, http.StatusTooManyRequests, send(tierRequest{ip: ip1, userID: user1}))
	})

	t.Run("an unknown tier gets the anonymous rate and the IP bucket", func(t *testing.T) {
		t.Parallel()
		send := newTierHandler(t, ports.RateLimitPolicy{
			UnauthedIP: burst(2),
			Identity: map[ports.Tier]ports.Rate{
				ports.TierAnonymous: burst(1),
				ports.TierMicrosoft: burst(10),
			},
		})
		require.Equal(t, http.StatusOK, send(tierRequest{ip: ip1, bearer: "future:" + user1}))
		require.Equal(t, http.StatusTooManyRequests, send(tierRequest{ip: ip1, bearer: "future:" + user1}))
		require.Equal(t, http.StatusTooManyRequests, send(tierRequest{ip: ip1, bearer: "future:" + user2}),
			"both requests spent the IP bucket")
	})

	t.Run("an unknown tier does not share the anonymous bucket", func(t *testing.T) {
		t.Parallel()
		send := newTierHandler(t, ports.RateLimitPolicy{
			UnauthedIP: burst(10),
			Identity:   map[ports.Tier]ports.Rate{ports.TierAnonymous: burst(1)},
		})
		require.Equal(t, http.StatusOK, send(tierRequest{ip: ip1, bearer: "future:" + user1}))
		require.Equal(t, http.StatusOK, send(tierRequest{ip: ip1, bearer: "anonymous:" + user1}))
	})
}
