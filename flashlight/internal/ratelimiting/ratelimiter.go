package ratelimiting

import (
	"fmt"
	"net"
	"net/http"
	"strings"
	"time"

	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/reporting"
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

func IPKeyFunc(r *http.Request) string {
	ctx := r.Context()

	xff := r.Header.Get("X-Forwarded-For")
	if xff == "" {
		logging.FromContext(ctx).WarnContext(ctx, "X-Forwarded-For header missing; using RemoteAddr")
		reporting.Report(
			ctx,
			fmt.Errorf("X-Forwarded-For header missing; using RemoteAddr"),
			map[string]string{
				"headerXForwardedFor": xff,
				"remoteAddr":          r.RemoteAddr,
				"method":              r.Method,
				"userAgent":           r.UserAgent(),
				"url":                 r.URL.String(),
			},
		)
		withoutPort := r.RemoteAddr

		portIndex := strings.IndexByte(r.RemoteAddr, ':')
		if portIndex != -1 {
			withoutPort = r.RemoteAddr[:portIndex]
		}

		return fmt.Sprintf("ip: %s", withoutPort)
	}

	// Split the header value by comma
	ips := strings.Split(xff, ",")
	clientIP := ""
	if len(ips) > 2 {
		// https://docs.cloud.google.com/load-balancing/docs/https#x-forwarded-for_header
		// If the incoming request already includes an X-Forwarded-For header, the load balancer appends its values to the existing header:
		// X-Forwarded-For: <existing-value>,<client-ip>,<load-balancer-ip>
		clientIP = ips[len(ips)-2]
	} else {
		clientIP = ips[0]
	}

	clientIP = strings.TrimSpace(clientIP)

	if clientIP == "" {
		logging.FromContext(ctx).WarnContext(ctx, "Failed to parse X-Forwarded-For header")
		reporting.Report(
			ctx,
			fmt.Errorf("failed to extract client IP from X-Forwarded-For header"),
			map[string]string{
				"headerXForwardedFor": xff,
				"remoteAddr":          r.RemoteAddr,
				"method":              r.Method,
				"userAgent":           r.UserAgent(),
				"url":                 r.URL.String(),
			},
		)
	}

	validatedIP := ""

	parsed := net.ParseIP(clientIP)
	if parsed == nil {
		logging.FromContext(ctx).WarnContext(ctx, "Failed to parse client IP from X-Forwarded-For header", "clientIP", clientIP)
		reporting.Report(
			ctx,
			fmt.Errorf("failed to parse client IP from X-Forwarded-For header"),
			map[string]string{
				"clientIP":            clientIP,
				"headerXForwardedFor": xff,
				"remoteAddr":          r.RemoteAddr,
				"method":              r.Method,
				"userAgent":           r.UserAgent(),
				"url":                 r.URL.String(),
			},
		)
		validatedIP = "<invalid>"
	} else {
		validatedIP = parsed.String()
	}

	return fmt.Sprintf("ip: %s", validatedIP)
}

func UserIDKeyFunc(r *http.Request) string {
	userID := r.Header.Get("X-User-Id")
	if userID == "" {
		userID = "<missing>"
	}
	return fmt.Sprintf("user-id: %.50s", userID)
}
