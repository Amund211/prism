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

			uuid := r.URL.Query().Get("uuid")
			if uuid == "" {
				uuid = "<missing>"
			}

			userId := r.Header.Get("X-User-Id")
			if userId == "" {
				userId = "<missing>"
			}

			userAgent := r.UserAgent()
			if userAgent == "" {
				userAgent = "<missing>"
			}

			requestLogger := logger.With(
				slog.String("correlationID", correlationID),
				slog.String("uuid", uuid),
				slog.String("userId", userId),
				slog.String("userAgent", userAgent),
				slog.String("methodPath", fmt.Sprintf("%s %s", r.Method, r.URL.Path)),
			)

			next(w, r.WithContext(AddToContext(ctx, requestLogger)))
		}
	}
}
