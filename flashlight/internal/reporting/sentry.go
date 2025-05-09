package reporting

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"regexp"
	"time"

	"github.com/Amund211/flashlight/internal/config"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/getsentry/sentry-go"
	sentryhttp "github.com/getsentry/sentry-go/http"
)

var uuidRx = regexp.MustCompile(`[0-9a-f]{8}-?([0-9a-f]{4}-?){3}[0-9a-f]{12}`)
var hostRx = regexp.MustCompile(`\[:{0,2}([0-9a-f]{0,4}:?){1,8}\]:\d+`)

func sanitizeError(err string) string {
	err = uuidRx.ReplaceAllString(err, "<uuid>")
	err = hostRx.ReplaceAllString(err, "<host>")
	return err
}

func Report(ctx context.Context, err error, extras ...map[string]string) {
	hub := sentry.GetHubFromContext(ctx)
	logger := logging.FromContext(ctx)
	if hub == nil {
		logger.Warn("Failed to get Sentry hub from context", "Error:", err, "Extras:", extras)
		return
	}

	logger.Error(
		"Reporting error to Sentry",
		slog.String("error", err.Error()),
		slog.Any("extras", extras),
	)

	hub.WithScope(func(scope *sentry.Scope) {
		meta := MetaFromContext(ctx)
		scope.SetTags(meta.tags)
		for key, value := range meta.extras {
			scope.SetExtra(key, value)
		}
		if meta.userID != "" {
			scope.SetUser(sentry.User{
				ID: meta.userID,
			})
		}
		scope.SetExtra("secondsSinceStart", time.Since(meta.startedAt).Seconds())

		for _, extra := range extras {
			if extra == nil {
				continue
			}
			for key, value := range extra {
				scope.SetExtra(key, value)
			}
		}

		if err == nil {
			err = errors.New("No error provided")
		}

		scope.SetFingerprint([]string{"{{ default }}", sanitizeError(err.Error())})
		hub.CaptureException(err)
	})
}

func addMetaMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		userAgent := r.UserAgent()
		if userAgent == "" {
			userAgent = "<missing>"
		}
		methodPath := fmt.Sprintf("%s %s", r.Method, r.URL.Path)

		ctx = AddTagsToContext(ctx,
			map[string]string{
				"userAgent":  userAgent,
				"methodPath": methodPath,
			},
		)

		ctx = setStartedAtInContext(ctx, time.Now())

		next(w, r.WithContext(ctx))
	}
}

func InitSentryMiddleware(sentryDSN string) (func(http.HandlerFunc) http.HandlerFunc, func(), error) {
	err := sentry.Init(sentry.ClientOptions{
		Dsn:              sentryDSN,
		EnableTracing:    true,
		TracesSampleRate: 1.0 / 100.0,
	})
	if err != nil {
		return nil, nil, err
	}

	sentryHandler := sentryhttp.New(sentryhttp.Options{})

	// Wrap sentry middleware in a http.HandlerFunc
	middleware := func(next http.HandlerFunc) http.HandlerFunc {
		withAddTags := addMetaMiddleware(next)
		return func(w http.ResponseWriter, r *http.Request) {
			sentryHandler.HandleFunc(withAddTags).ServeHTTP(w, r)
		}
	}

	flush := func() {
		sentry.Flush(5 * time.Second)
	}

	return middleware, flush, nil
}

func NewSentryMiddlewareOrMock(config config.Config) (func(http.HandlerFunc) http.HandlerFunc, func(), error) {
	if config.SentryDSN() != "" {
		return InitSentryMiddleware(config.SentryDSN())
	}

	if config.IsDevelopment() {
		middleware := func(next http.HandlerFunc) http.HandlerFunc {
			return next
		}
		flush := func() {}
		return middleware, flush, nil
	}

	return nil, nil, fmt.Errorf("Missing Sentry DSN in non-development environment")
}
