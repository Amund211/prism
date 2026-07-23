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
	requestCount            metric.Int64Counter
	requestDuration         metric.Float64Histogram
	blockedRequestCount     metric.Int64Counter
	ratelimitedRequestCount metric.Int64Counter
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

	blockedRequestCount, err := meter.Int64Counter(
		"ports/blocked_request_count",
		metric.WithDescription("Total number of blocked requests"),
	)
	if err != nil {
		panic(fmt.Errorf("failed to create blocked request count metric: %w", err))
	}

	ratelimitedRequestCount, err := meter.Int64Counter(
		"ports/ratelimited_request_count",
		metric.WithDescription("Total number of ratelimited requests"),
	)
	if err != nil {
		panic(fmt.Errorf("failed to create ratelimited request count metric: %w", err))
	}

	metrics = portsMetricsCollection{
		requestCount:            requestCount,
		requestDuration:         requestDuration,
		blockedRequestCount:     blockedRequestCount,
		ratelimitedRequestCount: ratelimitedRequestCount,
	}
}

// knownMethods bounds the cardinality of the "method" metric label. r.Method is
// client-controlled — Go's HTTP server accepts any valid HTTP token as a method,
// not just the standard verbs — so anything outside this allow-list is collapsed
// to "other" to keep handler × method series bounded regardless of input.
var knownMethods = map[string]struct{}{
	http.MethodGet:     {},
	http.MethodHead:    {},
	http.MethodPost:    {},
	http.MethodPut:     {},
	http.MethodPatch:   {},
	http.MethodDelete:  {},
	http.MethodConnect: {},
	http.MethodOptions: {},
	http.MethodTrace:   {},
}

func normalizeMethod(method string) string {
	if _, ok := knownMethods[method]; ok {
		return method
	}
	return "other"
}

func buildMetricsMiddleware(handler string) func(http.HandlerFunc) http.HandlerFunc {
	return func(next http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			ctx := r.Context()

			next(w, r)

			// NOTE: Only attach bounded attributes here. High-cardinality
			// values (user agent, IP hash, etc.) would blow past the
			// OpenTelemetry per-instrument cardinality limit (default 2000)
			// and collapse into a single otel.metric.overflow series. They
			// belong in logs/traces, not metric labels. Client type/version
			// are bounded: normalizeClient allowlists them into a small, fixed
			// set of valid pairs (kept short deliberately).
			attributes := []attribute.KeyValue{
				attribute.String("method", normalizeMethod(r.Method)),
				attribute.String("handler", handler),
			}
			attributes = append(attributes, GetClient(r).MetricAttributes()...)

			attributesOption := metric.WithAttributes(attributes...)

			metrics.requestCount.Add(ctx, 1, attributesOption)
			metrics.requestDuration.Record(ctx, time.Since(start).Seconds(), attributesOption)
		}
	}
}
