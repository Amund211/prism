package ports

import (
	"fmt"
	"log/slog"
	"net/http"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
)

type Rate struct {
	Refill ratelimiting.RefillPerSecond
	Burst  ratelimiting.BurstSize
}

// RateLimitPolicy sets the limits for one endpoint.
// UnauthedIP counts tier none and anonymous requests per IP.
// UnauthedIPLong is an optional second bucket on the same key, for a long window.
// Identity is keyed on (tier, identity). A tier not in the map uses TierAnonymous,
// which is required.
// IdentityLong is an optional second bucket on the identity key, for a long window.
// When set, it follows the same TierAnonymous fallback.
type RateLimitPolicy struct {
	UnauthedIP     Rate
	UnauthedIPLong *Rate
	Identity       map[Tier]Rate
	IdentityLong   map[Tier]Rate
}

type Tier string

const (
	// TierNone is a request without a bearer, keyed on X-User-Id.
	TierNone      Tier = "none"
	TierAnonymous Tier = Tier(domain.AuthSessionIdentityAnonymous)
	TierMicrosoft Tier = Tier(domain.AuthSessionIdentityMicrosoft)
)

var longIPRate = Rate{0.1, 200}

// Prism looks up all 16 players in a doubles/fours lobby at game start.
const prismLookupsPerGame = 16

var (
	// Short buckets allow a few games at once. Long buckets set the sustained
	// pace: microsoft 1 game per 2.2 min, anonymous and none 1 game per 8 min.
	PrismRateLimitPolicy = RateLimitPolicy{ // playerdata, tags, account
		UnauthedIP:     Rate{4, 120},
		UnauthedIPLong: &longIPRate,
		Identity: map[Tier]Rate{
			TierMicrosoft: {0.5, 4 * prismLookupsPerGame}, // {0.5, 64}
			TierAnonymous: {0.3, 3 * prismLookupsPerGame}, // {0.3, 48}
			// TODO: Reduce heavily as users move to clients with auth, and the
			// remaining traffic is mostly abuse.
			TierNone: {0.3, 3 * prismLookupsPerGame}, // {0.3, 48}
		},
		IdentityLong: map[Tier]Rate{
			TierMicrosoft: {prismLookupsPerGame / (2.2 * 60), 10 * prismLookupsPerGame}, // {0.121, 160}
			TierAnonymous: {prismLookupsPerGame / (8 * 60.0), 8 * prismLookupsPerGame},  // {0.0333, 128}
			TierNone:      {prismLookupsPerGame / (8 * 60.0), 8 * prismLookupsPerGame},  // {0.0333, 128}
		},
	}
	StatsRateLimitPolicy = RateLimitPolicy{ // history, wrapped
		UnauthedIP:     Rate{2, 60},
		UnauthedIPLong: &longIPRate,
		Identity: map[Tier]Rate{
			TierMicrosoft: {1, 60}, TierAnonymous: {0.5, 30}, TierNone: {0.25, 10},
		},
	}
	SessionsRateLimitPolicy = RateLimitPolicy{ // sessions, session-at
		UnauthedIP: Rate{2, 30},
		Identity: map[Tier]Rate{
			TierMicrosoft: {1, 20}, TierAnonymous: {0.5, 15}, TierNone: {0.25, 5},
		},
	}
)

func plainRateLimitExceeded(w http.ResponseWriter, r *http.Request) {
	http.Error(w, "Rate limit exceeded", http.StatusTooManyRequests)
}

func jsonRateLimitExceeded(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusTooManyRequests)
	w.Write([]byte(`{"success":false,"cause":"rate limit exceeded"}`))
}

// NewAuthRateLimitMiddleware builds the policy's limiters as one middleware.
// It must be mounted after the bearer middleware and panics on a request that
// did not pass through it. The returned func stops the limiters.
func NewAuthRateLimitMiddleware(policy RateLimitPolicy, onLimitExceeded http.HandlerFunc) (func(http.HandlerFunc) http.HandlerFunc, func()) {
	if _, ok := policy.Identity[TierAnonymous]; !ok {
		panic("rate limit policy needs an anonymous identity rate")
	}
	if _, ok := policy.IdentityLong[TierAnonymous]; len(policy.IdentityLong) > 0 && !ok {
		panic("rate limit policy needs an anonymous long identity rate")
	}

	var stops []func()
	newLimiter := func(rate Rate) ratelimiting.RateLimiter {
		limiter, stop := ratelimiting.NewTokenBucketRateLimiter(rate.Refill, rate.Burst)
		stops = append(stops, stop)
		return limiter
	}

	ipLimiter := newLimiter(policy.UnauthedIP)
	var ipLongLimiter ratelimiting.RateLimiter
	if policy.UnauthedIPLong != nil {
		ipLongLimiter = newLimiter(*policy.UnauthedIPLong)
	}
	identityLimiters := make(map[Tier]ratelimiting.RateLimiter, len(policy.Identity))
	for tier, rate := range policy.Identity {
		identityLimiters[tier] = newLimiter(rate)
	}
	identityLongLimiters := make(map[Tier]ratelimiting.RateLimiter, len(policy.IdentityLong))
	for tier, rate := range policy.IdentityLong {
		identityLongLimiters[tier] = newLimiter(rate)
	}

	stop := func() {
		for _, stop := range stops {
			stop()
		}
	}

	middleware := func(next http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			if !BearerCheckedFromContext(r.Context()) {
				panic("auth rate limit middleware mounted without the bearer middleware in front")
			}

			tier, identityKey := requestTier(r)

			identityLimiter, ok := identityLimiters[tier]
			if !ok {
				identityLimiter = identityLimiters[TierAnonymous]
			}
			identityLongLimiter, ok := identityLongLimiters[tier]
			if !ok {
				identityLongLimiter = identityLongLimiters[TierAnonymous]
			}

			if tier != TierMicrosoft {
				key := IPHashKeyFunc(r)
				if !ipLimiter.Consume(key) {
					rejectRateLimited(w, r, onLimitExceeded, tier, "ip", key)
					return
				}
				if ipLongLimiter != nil && !ipLongLimiter.Consume(key) {
					rejectRateLimited(w, r, onLimitExceeded, tier, "ip_long", key)
					return
				}
			}

			if !identityLimiter.Consume(identityKey) {
				rejectRateLimited(w, r, onLimitExceeded, tier, "identity", identityKey)
				return
			}
			if identityLongLimiter != nil && !identityLongLimiter.Consume(identityKey) {
				rejectRateLimited(w, r, onLimitExceeded, tier, "identity_long", identityKey)
				return
			}

			next(w, r)
		}
	}

	return middleware, stop
}

// requestTier returns the tier and the identity bucket key. An unknown tier
// keeps its own name, so it never shares a bucket with a known tier.
func requestTier(r *http.Request) (Tier, string) {
	auth, ok := AuthFromContext(r.Context())
	if !ok {
		return TierNone, fmt.Sprintf("%s: %s", TierNone, GetUserID(r).String())
	}
	tier := Tier(auth.IdentityType)
	return tier, fmt.Sprintf("%s: %s", tier, NewUserID(auth.IdentityKey).String())
}

func rejectRateLimited(w http.ResponseWriter, r *http.Request, onLimitExceeded http.HandlerFunc, tier Tier, scope, key string) {
	ctx := r.Context()

	logging.FromContext(ctx).InfoContext(ctx, "Rate limit exceeded",
		slog.String("tier", string(tier)),
		slog.String("scope", scope),
		slog.String("key", key),
	)

	metricTier := tier
	switch tier {
	case TierNone, TierAnonymous, TierMicrosoft:
	default:
		metricTier = "unknown"
	}
	attributes := []attribute.KeyValue{
		attribute.String("tier", string(metricTier)),
		attribute.String("scope", scope),
	}
	attributes = append(attributes, GetClient(r).MetricAttributes()...)
	metrics.ratelimitedRequestCount.Add(ctx, 1, metric.WithAttributes(attributes...))

	onLimitExceeded(w, r)
}
