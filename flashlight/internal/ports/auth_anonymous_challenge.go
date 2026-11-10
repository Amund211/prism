package ports

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"

	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/proofofwork"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
)

// anonymousChallengeRequest names the identity the caller intends to log in
// as. The challenge is bound to it, which is what lets the scheme stay
// stateless: see the comment on challengePayload.UserID.
type anonymousChallengeRequest struct {
	UserID string `json:"userId"`
}

// anonymousChallengeResponse is the wire shape of a minted proof-of-work
// challenge. challenge is opaque to the client — everything needed to
// solve it is in the other three fields, and difficulty is repeated here
// only so the client doesn't have to parse the blob (it also travels
// signed inside it, which is what verification reads).
//
// A client that doesn't recognize algorithm must fail rather than guess:
// that is what lets a future scheme be added without breaking anyone.
type anonymousChallengeResponse struct {
	Challenge        string `json:"challenge"`
	Algorithm        string `json:"algorithm"`
	Difficulty       int    `json:"difficulty"`
	ExpiresInSeconds int64  `json:"expiresInSeconds"`
}

// MakeAnonymousChallengeHandler returns a handler for
// POST /v1/auth/anonymous/challenge. Body: { userId }. Response: a signed
// challenge the caller must solve to log in as that userId.
//
// The challenge is stateless — signed, not stored — so this endpoint
// touches no database and holds nothing. It still gets a limiter of its
// own: it is unauthenticated, and it shouldn't be a free HMAC oracle.
func MakeAnonymousChallengeHandler(
	issueChallenge proofofwork.IssueChallenge,
	allowedOrigins *DomainSuffixes,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
	blocklistConfig BlocklistConfig,
) (http.HandlerFunc, func()) {
	// Same budget as the login endpoint it feeds: the handshake is one
	// challenge per login, so a caller that can't log in any faster has no
	// use for challenges any faster either.
	ipLimiter, stopIPLimiter := ratelimiting.NewTokenBucketRateLimiter(
		ratelimiting.RefillPerSecond(1),
		ratelimiting.BurstSize(60),
	)
	ipRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		ipLimiter,
		IPHashKeyFunc,
	)
	ipLimiterLong, stopIPLimiterLong := ratelimiting.NewTokenBucketRateLimiter(
		ratelimiting.RefillPerSecond(0.1),
		ratelimiting.BurstSize(200),
	)
	ipRateLimiterLong := ratelimiting.NewRequestBasedRateLimiter(
		ipLimiterLong,
		IPHashKeyFunc,
	)

	middleware := ComposeMiddlewares(
		NewRequestLoggerMiddleware(rootLogger),
		sentryMiddleware,
		BuildBlocklistMiddleware(blocklistConfig),
		buildMetricsMiddleware("auth-anonymous-challenge"),
		NewReportingMetaMiddleware("auth-anonymous-challenge"),
		BuildCORSMiddleware(allowedOrigins),
		NewRateLimitMiddleware(ipRateLimiter, makeOnAuthLimitExceeded(ipRateLimiter)),
		NewRateLimitMiddleware(ipRateLimiterLong, makeOnAuthLimitExceeded(ipRateLimiterLong)),
	)

	stop := func() {
		stopIPLimiter()
		stopIPLimiterLong()
	}

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		// Required for the same reason as on login, though the stakes are
		// lower here: a JSON content type is not CORS-safelisted, so
		// demanding it forces a preflight and keeps a page on an arbitrary
		// origin from spending a visitor's challenge budget — and with it
		// the visitor's ability to log in — from the visitor's own IP.
		if !hasJSONContentType(r) {
			logging.FromContext(ctx).InfoContext(ctx, "Rejected anonymous challenge with non-JSON content type",
				slog.String("contentType", r.Header.Get("Content-Type")),
			)
			http.Error(w, "Content-Type must be application/json", http.StatusUnsupportedMediaType)
			return
		}

		var body anonymousChallengeRequest
		if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, authBodyMaxBytes)).Decode(&body); err != nil {
			logging.FromContext(ctx).InfoContext(ctx, "Failed to decode anonymous challenge body", "error", err.Error())
			http.Error(w, "Invalid request body", http.StatusBadRequest)
			return
		}
		// The same validation as login, because the two have to agree on
		// what a userId is: a value accepted here and rejected there would
		// hand out challenges that can never be spent. Note the other half
		// of that agreement is challengeMaxLength, which has to cover the
		// largest blob any userId passing this check can mint.
		if !validAnonymousUserID(body.UserID) {
			http.Error(w, "Invalid userId", http.StatusBadRequest)
			return
		}

		client := GetClient(r)
		ipHash := GetIP(r).Hash()

		challenge, err := issueChallenge(body.UserID, ipHash, client.Type)
		if err != nil {
			logging.FromContext(ctx).ErrorContext(ctx, "Failed to issue anonymous challenge", "error", err.Error())
			reporting.Report(ctx, fmt.Errorf("issue anonymous challenge: %w", err))
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}

		// Difficulty is bounded by proofofwork.MaxDifficulty, so it is safe
		// as a metric attribute.
		metrics.powChallengeCount.Add(ctx, 1, metric.WithAttributes(
			append(client.MetricAttributes(), attribute.Int("difficulty", challenge.Difficulty))...,
		))

		writeAuthJSONResponse(ctx, w, "challenge", anonymousChallengeResponse{
			Challenge:        challenge.Value,
			Algorithm:        challenge.Algorithm,
			Difficulty:       challenge.Difficulty,
			ExpiresInSeconds: int64(challenge.ExpiresIn.Seconds()),
		})
	}

	return middleware(handler), stop
}
