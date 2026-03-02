package ports

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"slices"
	"time"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/google/uuid"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
)

func NewRequestLoggerMiddleware(logger *slog.Logger) func(next http.HandlerFunc) http.HandlerFunc {
	return func(next http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			ctx := r.Context()
			correlationID := uuid.New().String()

			userAgent := r.UserAgent()
			if userAgent == "" {
				userAgent = "<missing>"
			}

			requestLogger := logger.With(
				slog.String("correlationID", correlationID),
				slog.String("userAgent", userAgent),
				slog.String("methodPath", fmt.Sprintf("%s %s", r.Method, r.URL.Path)),
			)

			next(w, r.WithContext(logging.AddToContext(ctx, requestLogger)))
		}
	}
}

func IPHashKeyFunc(r *http.Request) string {
	return fmt.Sprintf("ip: %s", GetIPHash(r))
}

func UserIDKeyFunc(r *http.Request) string {
	return fmt.Sprintf("user-id: %s", GetUserID(r))
}

func NewRateLimitMiddleware(rateLimiter ratelimiting.RequestRateLimiter, onLimitExceeded http.HandlerFunc) func(http.HandlerFunc) http.HandlerFunc {
	return func(next http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			if !rateLimiter.Consume(r) {
				ctx := r.Context()
				userAgent := r.UserAgent()
				if userAgent == "" {
					userAgent = "<missing>"
				}
				userID := GetUserID(r)
				ipHash := GetIPHash(r)

				logging.FromContext(ctx).InfoContext(ctx, "Rate limit exceeded",
					slog.String("ipHash", ipHash),
					slog.String("userAgent", userAgent),
					slog.String("userId", userID),
				)

				attributes := []attribute.KeyValue{
					attribute.String("ip_hash", ipHash),
				}
				metrics.ratelimitedRequestCount.Add(ctx, 1, metric.WithAttributes(attributes...))

				onLimitExceeded(w, r)
				return
			}

			next(w, r)
		}
	}
}

func BuildRegisterUserVisitMiddleware(registerUserVisit app.RegisterUserVisit) func(http.HandlerFunc) http.HandlerFunc {
	return func(next http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			go func() {
				// NOTE: Since we're doing this in a goroutine, we want a context
				//       that won't get cancelled when the request ends
				ctx, cancel := context.WithTimeout(
					context.WithoutCancel(r.Context()),
					1*time.Second,
				)
				defer cancel()

				userID := GetUserID(r)

				_, _ = registerUserVisit(ctx, userID)
			}()

			next(w, r)
		}
	}
}

type BlocklistConfig struct {
	IPs        []string
	UserAgents []string
	UserIDs    []string
}

func BuildBlocklistMiddleware(config BlocklistConfig) func(http.HandlerFunc) http.HandlerFunc {
	// Pre-hash the IPs from the config so we can compare them with the hashed IP from the request
	hashedIPs := make([]string, len(config.IPs))
	for i, ip := range config.IPs {
		hashedIPs[i] = HashIP(ip)
	}

	return func(next http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			ctx := r.Context()
			ipHash := GetIPHash(r)
			userAgent := r.UserAgent()
			userID := GetUserID(r)

			badIP := slices.Contains(hashedIPs, ipHash)
			badUserAgent := slices.Contains(config.UserAgents, userAgent)
			badUserID := slices.Contains(config.UserIDs, userID)

			if badIP || badUserAgent || badUserID {
				// Log the blocked request with details
				logging.FromContext(ctx).InfoContext(ctx, "Blocked request",
					slog.String("ipHash", ipHash),
					slog.String("userAgent", userAgent),
					slog.String("userId", userID),
					slog.Bool("badIp", badIP),
					slog.Bool("badUserAgent", badUserAgent),
					slog.Bool("badUserId", badUserID),
				)

				// Record metric with blocking dimensions as labels
				attributes := []attribute.KeyValue{
					attribute.Bool("bad_ip", badIP),
					attribute.Bool("bad_user_agent", badUserAgent),
					attribute.Bool("bad_user_id", badUserID),
				}
				metrics.blockedRequestCount.Add(ctx, 1, metric.WithAttributes(attributes...))

				http.Error(w, `{"success": false, "detail": "This API does not allow third-party use. Reach out on the Prism discord if you have questions :^) (https://discord.gg/k4FGUnEHYg)"}`, http.StatusBadRequest)
				return
			}
			next(w, r)
		}
	}
}

func ComposeMiddlewares(middlewares ...func(http.HandlerFunc) http.HandlerFunc) func(http.HandlerFunc) http.HandlerFunc {
	if len(middlewares) == 1 {
		return middlewares[0]
	}
	first := middlewares[0]
	rest := ComposeMiddlewares(middlewares[1:]...)
	return func(h http.HandlerFunc) http.HandlerFunc {
		return first(rest(h))
	}
}
