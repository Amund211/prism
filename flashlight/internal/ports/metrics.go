package ports

import (
	"fmt"
	"net/http"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
)

type portsMetricsCollection struct {
	requestCount    metric.Int64Counter
	requestDuration metric.Float64Histogram
}

var metrics portsMetricsCollection

func init() {
	const name = "flashlight/ports"
	meter := otel.Meter(name)

	requestCount, err := meter.Int64Counter(
		"ports/request_count",
		metric.WithDescription("Total number of requests received"),
	)
	if err != nil {
		panic(fmt.Errorf("failed to create request count metric: %w", err))
	}

	requestDuration, err := meter.Float64Histogram(
		"ports/request_duration_seconds",
		metric.WithDescription("Processing time for received requests"),
		metric.WithUnit("s"),
	)
	if err != nil {
		panic(fmt.Errorf("failed to create request duration metric: %w", err))
	}

	metrics = portsMetricsCollection{
		requestCount:    requestCount,
		requestDuration: requestDuration,
	}
}

func buildMetricsMiddleware() func(http.HandlerFunc) http.HandlerFunc {
	return func(next http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			ctx := r.Context()

			userAgent := r.UserAgent()
			if userAgent == "" {
				userAgent = "<missing>"
			}

			// NOTE: Potentially high cardinality label
			userId := r.Header.Get("X-User-Id")
			if userId == "" {
				userId = "<missing>"
			}

			next(w, r)

			attributes := []attribute.KeyValue{
				attribute.String("method", r.Method),
				attribute.String("path", r.URL.Path),
				attribute.String("user_agent", userAgent),
				attribute.String("user_id", userId),
			}

			attributesOption := metric.WithAttributes(attributes...)

			metrics.requestCount.Add(ctx, 1, attributesOption)
			metrics.requestDuration.Record(ctx, time.Since(start).Seconds(), attributesOption)
		}
	}
}
