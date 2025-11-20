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
		// Using the default buckets, but divided by 1000 to keep the unit as s instead of ms.
		metric.WithExplicitBucketBoundaries(0, 0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10),
	)
	if err != nil {
		panic(fmt.Errorf("failed to create request duration metric: %w", err))
	}

	metrics = portsMetricsCollection{
		requestCount:    requestCount,
		requestDuration: requestDuration,
	}
}

func buildMetricsMiddleware(handler string) func(http.HandlerFunc) http.HandlerFunc {
	return func(next http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			ctx := r.Context()

			userAgent := r.UserAgent()
			if userAgent == "" {
				userAgent = "<missing>"
			}

			// NOTE: Potentially high cardinality label
			userID := r.Header.Get("X-User-Id")
			if userID == "" {
				userID = "<missing>"
			}

			next(w, r)

			attributes := []attribute.KeyValue{
				attribute.String("method", r.Method),
				attribute.String("handler", handler),
				attribute.String("user_agent", userAgent),
				attribute.String("user_id", userID),
			}

			attributesOption := metric.WithAttributes(attributes...)

			metrics.requestCount.Add(ctx, 1, attributesOption)
			metrics.requestDuration.Record(ctx, time.Since(start).Seconds(), attributesOption)
		}
	}
}
