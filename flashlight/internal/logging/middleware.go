package logging

import (
	"fmt"
	"log/slog"
	"net/http"

	"github.com/google/uuid"
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

			next(w, r.WithContext(AddToContext(ctx, requestLogger)))
		}
	}
}
