package server

import (
	"net/http"

	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
)

func NewRateLimitMiddleware(rateLimiter ratelimiting.RequestRateLimiter) func(http.HandlerFunc) http.HandlerFunc {
	return func(next http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			if !rateLimiter.Consume(r) {
				logger := logging.FromContext(r.Context())
				statusCode := writeErrorResponse(r.Context(), w, e.RatelimitExceededError)
				logger.Info("Returning response", "statusCode", statusCode, "reason", "ratelimit exceeded", "key", rateLimiter.KeyFor(r))
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
