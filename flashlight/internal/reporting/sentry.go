package reporting

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"regexp"
	"time"

	"github.com/getsentry/sentry-go"
	sentryhttp "github.com/getsentry/sentry-go/http"

	"github.com/Amund211/flashlight/internal/config"
	"github.com/Amund211/flashlight/internal/logging"
)

var uuidRx = regexp.MustCompile(`[0-9a-f]{8}-?([0-9a-f]{4}-?){3}[0-9a-f]{12}`)
var hostRx = regexp.MustCompile(`\[:{0,2}([0-9a-f]{0,4}:?){1,8}\]:\d+`)
var usernameRequestRx = regexp.MustCompile(`("https://api\.mojang\.com/users/profiles/minecraft/)[^\s]+?"`)

// invalidUUIDInputRx matches the errors returned by strutils.NormalizeUUID for
// bad input, scrubbing the user-supplied value quoted after "input: ". The
// value is high-cardinality client input, so keeping it out of the fingerprint
// keeps these grouped together.
var invalidUUIDInputRx = regexp.MustCompile(`((?:invalid character in UUID|normalized UUID has incorrect length)\. input: ').*'`)

func sanitizeError(err string) string {
	err = uuidRx.ReplaceAllString(err, "<uuid>")
	err = hostRx.ReplaceAllString(err, "<host>")
	err = usernameRequestRx.ReplaceAllString(err, `$1<username>"`)
	err = invalidUUIDInputRx.ReplaceAllString(err, `${1}<value>'`)
	return err
}

func Report(ctx context.Context, err error, extras ...map[string]string) {
	hub := sentry.GetHubFromContext(ctx)
	if hub == nil {
		logging.FromContext(ctx).WarnContext(ctx, "Failed to get Sentry hub from context", "Error:", err, "Extras:", extras)
		return
	}

	logging.FromContext(ctx).ErrorContext(
		ctx,
		"Reporting error to Sentry",
		slog.String("error", err.Error()),
		slog.Any("extras", extras),
	)

	hub.WithScope(func(scope *sentry.Scope) {
		meta := MetaFromContext(ctx)
		scope.SetTags(meta.tags)

		scope.SetContext("timing", map[string]interface{}{
			"secondsSinceStart": time.Since(meta.startedAt).Seconds(),
		})

		metaExtras := make(map[string]interface{})
		for key, value := range meta.extras {
			metaExtras[key] = value
		}
		scope.SetContext("from_context", metaExtras)

		if meta.userID != "" {
			scope.SetUser(sentry.User{
				ID: meta.userID,
			})
		}

		eventExtras := make(map[string]interface{})
		for _, extra := range extras {
			if extra == nil {
				continue
			}
			for key, value := range extra {
				eventExtras[key] = value
			}
		}
		scope.SetContext("from_event", eventExtras)

		if err == nil {
			err = errors.New("no error provided")
		}

		scope.SetFingerprint([]string{"{{ default }}", sanitizeError(err.Error())})
		hub.CaptureException(err)
	})
}

func InitSentryMiddleware(sentryDSN string) (func(http.HandlerFunc) http.HandlerFunc, func(time.Duration), error) {
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
		return func(w http.ResponseWriter, r *http.Request) {
			sentryHandler.HandleFunc(next).ServeHTTP(w, r)
		}
	}

	flush := func(timeout time.Duration) {
		sentry.Flush(timeout)
	}

	return middleware, flush, nil
}

func NewSentryMiddlewareOrMock(config config.Config) (func(http.HandlerFunc) http.HandlerFunc, func(time.Duration), error) {
	if config.SentryDSN() != "" {
		return InitSentryMiddleware(config.SentryDSN())
	}

	if config.IsDevelopment() {
		middleware := func(next http.HandlerFunc) http.HandlerFunc {
			return next
		}
		flush := func(time.Duration) {}
		return middleware, flush, nil
	}

	return nil, nil, fmt.Errorf("missing Sentry DSN in non-development environment")
}
