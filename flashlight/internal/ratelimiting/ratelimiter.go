package ratelimiting

import (
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/jellydator/ttlcache/v3"
	"golang.org/x/time/rate"
)

type RateLimiter interface {
	Consume(key string) bool
}

type tokenBucketRateLimiter struct {
	limiterByIP     *ttlcache.Cache[string, *rate.Limiter]
	refillPerSecond int
	burstSize       int
}

func (rateLimiter *tokenBucketRateLimiter) Consume(key string) bool {
	limiter, _ := rateLimiter.limiterByIP.GetOrSet(key, rate.NewLimiter(rate.Limit(rateLimiter.refillPerSecond), rateLimiter.burstSize))
	return limiter.Value().Allow()
}

type RefillPerSecond int
type BurstSize int

func NewTokenBucketRateLimiter(refillPerSecond RefillPerSecond, burstSize BurstSize) (RateLimiter, func()) {
	limiterTTLCache := ttlcache.New[string, *rate.Limiter](
		ttlcache.WithTTL[string, *rate.Limiter](30 * time.Minute),
	)
	go limiterTTLCache.Start()

	return &tokenBucketRateLimiter{
		limiterByIP:     limiterTTLCache,
		refillPerSecond: int(refillPerSecond),
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

func IPKeyFunc(r *http.Request) string {
	withoutPort := r.RemoteAddr

	portIndex := strings.IndexByte(r.RemoteAddr, ':')
	if portIndex != -1 {
		withoutPort = r.RemoteAddr[:portIndex]
	}

	return fmt.Sprintf("ip: %s", withoutPort)
}

func UserIDKeyFunc(r *http.Request) string {
	userID := r.Header.Get("X-User-Id")
	if userID == "" {
		userID = "<missing>"
	}
	return fmt.Sprintf("user-id: %.50s", userID)
}
