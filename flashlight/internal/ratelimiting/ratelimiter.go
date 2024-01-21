package ratelimiting

import (
    "time"

    "github.com/jellydator/ttlcache/v3"
    "golang.org/x/time/rate"
)

type RateLimiter interface {
	Allow(key string) bool
}

type ipBasedRateLimiter struct {
	limiterByIP     *ttlcache.Cache[string, *rate.Limiter]
	refillPerSecond int
	burstSize       int
}

func (rateLimiter ipBasedRateLimiter) Allow(key string) bool {
	limiter, _ := rateLimiter.limiterByIP.GetOrSet(key, rate.NewLimiter(rate.Limit(rateLimiter.refillPerSecond), rateLimiter.burstSize))
	return limiter.Value().Allow()
}

func NewIPBasedRateLimiter(refillPerSecond int, burstSize int) RateLimiter {
	limiterTTLCache := ttlcache.New[string, *rate.Limiter](
		ttlcache.WithTTL[string, *rate.Limiter](30 * time.Minute),
	)
	go limiterTTLCache.Start()
	return ipBasedRateLimiter{limiterByIP: limiterTTLCache, refillPerSecond: 2, burstSize: 120}
}
