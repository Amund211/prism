package ratelimiting

import (
	"net/http"
	"time"

	"github.com/jellydator/ttlcache/v3"
	"golang.org/x/time/rate"
)

type RateLimiter interface {
	Consume(key string) bool
}

type tokenBucketRateLimiter struct {
	limiterByIP     *ttlcache.Cache[string, *rate.Limiter]
	refillPerSecond float64
	burstSize       int
}

func (rateLimiter *tokenBucketRateLimiter) Consume(key string) bool {
	limiter, _ := rateLimiter.limiterByIP.GetOrSet(key, rate.NewLimiter(rate.Limit(rateLimiter.refillPerSecond), rateLimiter.burstSize))
	return limiter.Value().Allow()
}

type RefillPerSecond float64
type BurstSize int

func NewTokenBucketRateLimiter(refillPerSecond RefillPerSecond, burstSize BurstSize) (RateLimiter, func()) {
	limiterTTLCache := ttlcache.New[string, *rate.Limiter](
		ttlcache.WithTTL[string, *rate.Limiter](30 * time.Minute),
	)
	go limiterTTLCache.Start()

	return &tokenBucketRateLimiter{
		limiterByIP:     limiterTTLCache,
		refillPerSecond: float64(refillPerSecond),
		burstSize:       int(burstSize),
	}, limiterTTLCache.Stop
}

type RequestRateLimiter interface {
	Consume(r *http.Request) bool
	KeyFor(r *http.Request) string
}

type requestBasedRateLimiter struct {
	limiter RateLimiter
	keyFunc func(r *http.Request) string
}

func (rateLimiter *requestBasedRateLimiter) Consume(r *http.Request) bool {
	return rateLimiter.limiter.Consume(rateLimiter.keyFunc(r))
}

func (rateLimiter *requestBasedRateLimiter) KeyFor(r *http.Request) string {
	return rateLimiter.keyFunc(r)
}

func NewRequestBasedRateLimiter(limiter RateLimiter, keyFunc func(r *http.Request) string) RequestRateLimiter {
	return &requestBasedRateLimiter{
		limiter: limiter,
		keyFunc: keyFunc,
	}
}
