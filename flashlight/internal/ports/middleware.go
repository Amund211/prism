package ports

import (
	"context"
	"fmt"
	"net/http"
	"slices"
	"time"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/ratelimiting"
)

func IPKeyFunc(r *http.Request) string {
	return fmt.Sprintf("ip: %s", GetIP(r))
}

func UserIDKeyFunc(r *http.Request) string {
	return fmt.Sprintf("user-id: %s", GetUserID(r))
}

func NewRateLimitMiddleware(rateLimiter ratelimiting.RequestRateLimiter, onLimitExceeded http.HandlerFunc) func(http.HandlerFunc) http.HandlerFunc {
	return func(next http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			if !rateLimiter.Consume(r) {
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
	return func(next http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			if slices.Contains(config.IPs, GetIP(r)) ||
				slices.Contains(config.UserAgents, r.UserAgent()) ||
				slices.Contains(config.UserIDs, GetUserID(r)) {
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
