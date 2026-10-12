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
// Identity is keyed on (tier, identity). A tier not in the map uses TierAnonymous,
// which is required.
type RateLimitPolicy struct {
	UnauthedIP Rate
	Identity   map[Tier]Rate
}

type Tier string

const (
	// TierNone is a request without a bearer, keyed on X-User-Id.
	TierNone      Tier = "none"
	TierAnonymous Tier = Tier(domain.AuthSessionIdentityAnonymous)
	TierMicrosoft Tier = Tier(domain.AuthSessionIdentityMicrosoft)
)

var (
	PrismRateLimitPolicy = RateLimitPolicy{ // playerdata, tags, account
		UnauthedIP: Rate{4, 120},
		Identity: map[Tier]Rate{
			TierMicrosoft: {2, 120}, TierAnonymous: {1.5, 80}, TierNone: {1, 48},
		},
	}
	StatsRateLimitPolicy = RateLimitPolicy{ // history, wrapped
		UnauthedIP: Rate{2, 60},
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

// NewAuthRateLimitMiddleware builds the policy's limiters as one middleware.
// It must be mounted after the bearer middleware and panics on a request that
// did not pass through it. The returned func stops the limiters.
func NewAuthRateLimitMiddleware(policy RateLimitPolicy, onLimitExceeded http.HandlerFunc) (func(http.HandlerFunc) http.HandlerFunc, func()) {
	if _, ok := policy.Identity[TierAnonymous]; !ok {
		panic("rate limit policy needs an anonymous identity rate")
	}

	var stops []func()
	newLimiter := func(rate Rate) ratelimiting.RateLimiter {
		limiter, stop := ratelimiting.NewTokenBucketRateLimiter(rate.Refill, rate.Burst)
		stops = append(stops, stop)
		return limiter
	}

	ipLimiter := newLimiter(policy.UnauthedIP)
	identityLimiters := make(map[Tier]ratelimiting.RateLimiter, len(policy.Identity))
	for tier, rate := range policy.Identity {
		identityLimiters[tier] = newLimiter(rate)
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

			if tier != TierMicrosoft {
				if key := IPHashKeyFunc(r); !ipLimiter.Consume(key) {
					rejectRateLimited(w, r, onLimitExceeded, tier, "ip", key)
					return
				}
			}

			if !identityLimiter.Consume(identityKey) {
				rejectRateLimited(w, r, onLimitExceeded, tier, "identity", identityKey)
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
