package ports

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"slices"
	"time"

	"github.com/google/uuid"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
)

func NewRequestLoggerMiddleware(logger *slog.Logger) func(next http.HandlerFunc) http.HandlerFunc {
	return func(next http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			ctx := r.Context()
			correlationID := "corr_" + uuid.New().String()

			userAgent := r.UserAgent()

			userID := GetUserID(r)

			client := GetClient(r)

			requestLogger := logger.With(
				slog.String("correlationID", correlationID),
				slog.String("ipHash", GetIP(r).Hash()),
				slog.String("userAgent", userAgent),
				slog.String("methodPath", fmt.Sprintf("%s %s", r.Method, r.URL.Path)),
				slog.String("userId", userID.String()),
				slog.String("lowCardinalityUserId", userID.LowCardinalityString()),
				slog.String("clientType", client.Type),
				slog.String("clientVersion", client.Version),
			)

			start := time.Now()
			ctx = logging.AddToContext(ctx, requestLogger)

			logging.FromContext(ctx).InfoContext(ctx, "Normalized client info",
				slog.String("rawClientType", client.RawType),
				slog.String("rawClientVersion", client.RawVersion),
			)

			logging.FromContext(ctx).InfoContext(ctx, "Handling request")
			defer func() {
				if err := recover(); err != nil {
					logging.FromContext(ctx).ErrorContext(
						ctx,
						"Panic occurred while handling request",
						slog.Any("error", err),
						slog.Duration("duration", time.Since(start)),
					)
					panic(err)
				}

				logging.FromContext(ctx).InfoContext(
					ctx,
					"Finished handling request",
					slog.Duration("duration", time.Since(start)),
				)
			}()

			next(w, r.WithContext(ctx))
		}
	}
}

func IPHashKeyFunc(r *http.Request) string {
	return fmt.Sprintf("ip: %s", GetIP(r).Hash())
}

// UserIDKeyFunc keys the per-user rate limiters on the verified identity, falling
// back to the self-asserted X-User-Id header. Needs the bearer middleware ahead
// of the limiter. Never key on the session id — an identity holds any number of
// sessions, so that would mint quota per login.
//
// The anonymous tier shares the fallback's namespace on purpose: its
// identity_key *is* the userId from the header, so a separate key would be a
// second budget, claimable by dropping the Authorization header.
func UserIDKeyFunc(r *http.Request) string {
	auth, ok := AuthFromContext(r.Context())
	if !ok {
		return fmt.Sprintf("user-id: %s", GetUserID(r).String())
	}

	switch auth.IdentityType {
	case domain.AuthSessionIdentityAnonymous:
		return fmt.Sprintf("user-id: %s", NewUserID(auth.IdentityKey).String())
	default:
		// Unknown tiers get isolated rather than poured in above.
		return fmt.Sprintf("identity: %s: %s", auth.IdentityType, NewUserID(auth.IdentityKey).String())
	}
}

func NewRateLimitMiddleware(rateLimiter ratelimiting.RequestRateLimiter, onLimitExceeded http.HandlerFunc) func(http.HandlerFunc) http.HandlerFunc {
	return func(next http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			if !rateLimiter.Consume(r) {
				ctx := r.Context()
				userAgent := r.UserAgent()
				userID := GetUserID(r)
				ipHash := GetIP(r).Hash()

				logging.FromContext(ctx).InfoContext(ctx, "Rate limit exceeded",
					slog.String("ipHash", ipHash),
					slog.String("userAgent", userAgent),
					slog.String("userId", userID.String()),
				)

				// NOTE: ip_hash is high-cardinality and is captured in the log
				// above; keep it off the metric to stay under the OpenTelemetry
				// cardinality limit. Client type/version are bounded (allowlisted).
				metrics.ratelimitedRequestCount.Add(ctx, 1,
					metric.WithAttributes(GetClient(r).MetricAttributes()...),
				)

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
				ipHash := GetIP(r).Hash()
				userAgent := r.UserAgent()

				_, _ = registerUserVisit(ctx, userID.String(), ipHash, userAgent)
			}()

			next(w, r)
		}
	}
}

type BlocklistConfig struct {
	IPs          []string
	UserAgents   []string
	UserIDs      []string
	SHA256HexIPs []string
}

func BuildBlocklistMiddleware(config BlocklistConfig) func(http.HandlerFunc) http.HandlerFunc {
	// Pre-hash the IPs from the config so we can compare them with the hashed IP from the request
	hashedIPs := make([]string, len(config.IPs)+len(config.SHA256HexIPs))
	for i, ip := range config.IPs {
		hashedIPs[i] = IP(ip).Hash()
	}
	// Add the pre-hashed IPs to the same list
	copy(hashedIPs[len(config.IPs):], config.SHA256HexIPs)

	return func(next http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			ctx := r.Context()
			ipHash := GetIP(r).Hash()
			userAgent := r.UserAgent()
			userID := GetUserID(r)

			badIP := slices.Contains(hashedIPs, ipHash)
			badUserAgent := slices.Contains(config.UserAgents, userAgent)
			badUserID := slices.Contains(config.UserIDs, userID.String())

			if badIP || badUserAgent || badUserID {
				// Log the blocked request with details
				logging.FromContext(ctx).InfoContext(ctx, "Blocked request",
					slog.String("ipHash", ipHash),
					slog.String("userAgent", userAgent),
					slog.String("userId", userID.String()),
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
				attributes = append(attributes, GetClient(r).MetricAttributes()...)
				metrics.blockedRequestCount.Add(ctx, 1, metric.WithAttributes(attributes...))

				http.Error(w, `{"success": false, "detail": "This API does not allow third-party use. Reach out on the Prism discord if you have questions :^) (https://discord.gg/k4FGUnEHYg)"}`, http.StatusBadRequest)
				return
			}
			next(w, r)
		}
	}
}

func NewReportingMetaMiddleware(port string) func(http.HandlerFunc) http.HandlerFunc {
	return func(next http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			ctx := r.Context()

			userAgent := r.UserAgent()
			methodPath := fmt.Sprintf("%s %s", r.Method, r.URL.Path)
			client := GetClient(r)

			ctx = reporting.AddTagsToContext(ctx,
				map[string]string{
					"port":          port,
					"userAgent":     userAgent,
					"methodPath":    methodPath,
					"clientType":    client.Type,
					"clientVersion": client.Version,
				},
			)

			ctx = reporting.SetStartedAtInContext(ctx, time.Now())
			ctx = reporting.SetUserIDInContext(ctx, GetUserID(r).String())

			next(w, r.WithContext(ctx))
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
