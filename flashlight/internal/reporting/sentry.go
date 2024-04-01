package reporting

import (
	"context"
	"log"
	"net/http"
	"time"

	"github.com/getsentry/sentry-go"
	sentryhttp "github.com/getsentry/sentry-go/http"
)

func Report(ctx context.Context, err error, message *string, extra map[string]string) {
	hub := sentry.GetHubFromContext(ctx)
	if hub == nil {
		log.Println("Failed to get Sentry hub from context")
		return
	}

	hub.WithScope(func(scope *sentry.Scope) {
		if extra != nil {
			for key, value := range extra {
				scope.SetExtra(key, value)
			}
		}

		if err == nil {
			capturedMessage := "No message/error provided"
			if message != nil {
				capturedMessage = *message
			}
			hub.CaptureMessage(capturedMessage)
			return
		}

		if message != nil {
			scope.SetExtra("message", *message)
		}
		hub.CaptureException(err)
	})
}

func addTagsMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		hub := sentry.GetHubFromContext(r.Context())
		if hub == nil {
			log.Println("Failed to get Sentry hub from context")
			next(w, r)
			return
		}

		hub.ConfigureScope(func(scope *sentry.Scope) {
			scope.SetTag("user-agent", r.Header.Get("User-Agent"))

			uuid := r.URL.Query().Get("uuid")
			if uuid == "" {
				uuid = "<missing>"
			}
			scope.SetTag("uuid", uuid)

			userId := r.Header.Get("X-User-Id")
			if userId != "" {
				scope.SetUser(sentry.User{ID: userId})
			}
		})

		next(w, r)
	}
}

func InitSentryMiddleware(sentryDSN string) (func(http.HandlerFunc) http.HandlerFunc, func(), error) {
	err := sentry.Init(sentry.ClientOptions{
		Dsn:           sentryDSN,
		EnableTracing: true,
		// Set TracesSampleRate to 1.0 to capture 100%
		// of transactions for performance monitoring.
		// We recommend adjusting this value in production,
		TracesSampleRate: 1.0,
	})
	if err != nil {
		return nil, nil, err
	}

	sentryHandler := sentryhttp.New(sentryhttp.Options{})

	// Wrap sentry middleware in a http.HandlerFunc
	middleware := func(next http.HandlerFunc) http.HandlerFunc {
		withAddTags := addTagsMiddleware(next)
		return func(w http.ResponseWriter, r *http.Request) {
			sentryHandler.HandleFunc(withAddTags).ServeHTTP(w, r)
		}
	}

	flush := func() {
		sentry.Flush(5 * time.Second)
	}

	return middleware, flush, nil
}
