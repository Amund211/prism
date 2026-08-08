package ports

import (
	"context"
	"fmt"
	"net/http"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"

	"github.com/Amund211/flashlight/internal/proofofwork"
)

type portsMetricsCollection struct {
	requestCount            metric.Int64Counter
	requestDuration         metric.Float64Histogram
	blockedRequestCount     metric.Int64Counter
	ratelimitedRequestCount metric.Int64Counter
	powChallengeCount       metric.Int64Counter
	powChallengeAge         metric.Float64Histogram
	powRejectedLoginCount   metric.Int64Counter
}

// powOutcomeAccepted labels an age sample from a proof that verified. Every
// other value is a proofofwork.RejectionReason, so both pow metrics draw on
// one bounded vocabulary.
const powOutcomeAccepted = "ok"

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

	// Proof-of-work difficulty is a dial we turn from the server with no
	// client release, and a dial with no gauge isn't tunable. These two are
	// what tells us whether a difficulty change did anything and whether it
	// broke a client: issuance carries the difficulty it handed out, and
	// rejections carry the cause.
	powChallengeCount, err := meter.Int64Counter(
		"ports/pow_challenge_count",
		metric.WithDescription("Total number of proof-of-work challenges issued, by difficulty"),
	)
	if err != nil {
		panic(fmt.Errorf("failed to create pow challenge count metric: %w", err))
	}

	// What the difficulty costs a real client — the number no local
	// benchmark answers, since real clients are Windows machines running
	// CPython on whatever CPU came with the laptop.
	//
	// Attributed by difficulty because an age aggregated across mixed
	// difficulties answers nothing: a rise is equally explained by "clients
	// got slower" and "we asked for more work", and those have opposite
	// responses. Attributed, it is a cost curve.
	//
	// Read outcome="ok" next to outcome="expired" and
	// pow_rejected_login_count{reason="expired"}: only challenges that come
	// back are sampled, so a difficulty past what clients can finish makes
	// outcome="ok" look *better* as the slow half stops reporting.
	powChallengeAge, err := meter.Float64Histogram(
		"ports/pow_challenge_age_seconds",
		metric.WithDescription("Age of a proof-of-work challenge when presented at login (mint to arrival, including both round trips and the client's solve), by difficulty and outcome"),
		metric.WithUnit("s"),
		// Against challengeTTL rather than copied from requestDuration, whose
		// 10s ceiling would dump most of the range into the overflow bucket.
		// Fine below 1s because difficulty 0 is nearly a pure round trip, and
		// past 60s so an expired challenge that just missed is distinguishable
		// from a resumed laptop replaying a stale blob.
		metric.WithExplicitBucketBoundaries(0, 0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 15, 30, 45, 60, 75, 90, 120, 300),
	)
	if err != nil {
		panic(fmt.Errorf("failed to create pow challenge age metric: %w", err))
	}

	powRejectedLoginCount, err := meter.Int64Counter(
		"ports/pow_rejected_login_count",
		metric.WithDescription("Total number of anonymous logins rejected by proof-of-work verification, by cause"),
	)
	if err != nil {
		panic(fmt.Errorf("failed to create pow rejected login count metric: %w", err))
	}

	metrics = portsMetricsCollection{
		requestCount:            requestCount,
		requestDuration:         requestDuration,
		blockedRequestCount:     blockedRequestCount,
		ratelimitedRequestCount: ratelimitedRequestCount,
		powChallengeCount:       powChallengeCount,
		powChallengeAge:         powChallengeAge,
		powRejectedLoginCount:   powRejectedLoginCount,
	}
}

// recordPowChallengeAge samples how long a challenge took to come back.
// Difficulty is bounded by proofofwork.MaxDifficulty at mint time, so it is
// safe as an attribute.
func recordPowChallengeAge(ctx context.Context, r *http.Request, challenge proofofwork.SignedChallenge, outcome string) {
	age := challenge.Age()
	if age < 0 {
		// Our clock stepping backwards, not a measurement — and one negative
		// sample drags this instrument's sum for the life of the process.
		return
	}

	metrics.powChallengeAge.Record(ctx, age.Seconds(), metric.WithAttributes(
		append(GetClient(r).MetricAttributes(),
			attribute.Int("difficulty", challenge.Difficulty()),
			attribute.String("outcome", outcome),
		)...,
	))
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
