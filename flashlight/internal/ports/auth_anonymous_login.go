package ports

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"mime"
	"net/http"
	"time"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/proofofwork"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
)

type anonymousLoginRequest struct {
	UserID string `json:"userId"`
	// Challenge is the opaque blob handed out by
	// POST /v1/auth/anonymous/challenge, and Solution is the client's
	// answer to it. Both are mandatory: the handshake ships required and
	// the work ships at zero, because prism has a months-long upgrade tail
	// and a no-proof path attackers can use is the same as having no
	// proof-of-work at all.
	Challenge string `json:"challenge"`
	Solution  string `json:"solution"`
}

// userIDMaxLength is the hard cap above which we reject the request.
// The legacy X-User-Id header silently truncates at 50 chars
// (internal/ports/userid.go) and real overlay-generated user_ids are
// 32 chars (uuid4 hex), so 100 is comfortably above expected traffic.
const userIDMaxLength = 100

// challengeMaxLength and solutionMaxLength bound the proof-of-work fields
// before we hash anything. A solution is a counter the client incremented
// until the hash came out right, which stays short even at the sanity-ceiling
// difficulty.
//
// The challenge cap has to clear **everything the mint can produce**, or the
// challenge endpoint hands out blobs login rejects on shape and the handshake
// can never complete. It is not userIDMaxLength plus a constant: the payload
// is marshalled with encoding/json, which escapes `&`, `<`, `>` and control
// characters to six bytes each, so a legal 100-byte userId can contribute 600
// bytes before base64. Worst case today is 1116 bytes; the headroom here
// covers a field or two being added to challengePayload later. Pinned by
// TestAnonymousLoginProofOfWork/"challengeMaxLength covers everything the
// mint can produce".
const (
	challengeMaxLength = 1280
	solutionMaxLength  = 128
)

// authBodyMaxBytes comfortably fits the largest legal body on either
// anonymous endpoint — a 100-char userId, a challenge blob and a solution,
// all capped above — with room for the JSON around them.
const authBodyMaxBytes = 2048

// validAnonymousUserID applies the shared shape check. The challenge and
// login endpoints must agree on it exactly: the userId travels signed
// inside the challenge and is compared byte for byte on the way back in.
func validAnonymousUserID(userID string) bool {
	return userID != "" && len(userID) <= userIDMaxLength
}

// hasJSONContentType reports whether the request declares a JSON body.
// Parameters are allowed (application/json; charset=utf-8); a missing,
// malformed or non-JSON header is not.
func hasJSONContentType(r *http.Request) bool {
	mediaType, _, err := mime.ParseMediaType(r.Header.Get("Content-Type"))
	if err != nil {
		return false
	}
	return mediaType == "application/json"
}

// rejectProofOfWork refuses a login whose proof didn't verify. Every cause
// gets the same status: they differ only in what the client should have done
// differently, and the answer is the same for all of them — fetch a fresh
// challenge and try again (with backoff; a client that hot-loops on 403 is a
// client that rate-limits itself out).
func rejectProofOfWork(ctx context.Context, w http.ResponseWriter, r *http.Request, err error) {
	reason := proofofwork.RejectionReason(err)
	logging.FromContext(ctx).InfoContext(ctx, "Rejected anonymous login proof of work",
		slog.String("reason", reason),
		slog.String("error", err.Error()),
	)
	metrics.powRejectedLoginCount.Add(ctx, 1, metric.WithAttributes(
		append(GetClient(r).MetricAttributes(), attribute.String("reason", reason))...,
	))
	http.Error(w, "Invalid proof of work", http.StatusForbidden)
}

// MakeAnonymousLoginHandler returns a handler for POST /v1/auth/anonymous/login.
// Body: { userId, challenge, solution }. Response: a fresh session payload.
func MakeAnonymousLoginHandler(
	login app.AnonymousLogin,
	parseChallenge proofofwork.ParseChallenge,
	nowFunc func() time.Time,
	allowedOrigins *DomainSuffixes,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
	blocklistConfig BlocklistConfig,
) (http.HandlerFunc, func()) {
	// A login is cheap now that it touches no database — one HMAC to verify
	// the proof and one to sign the handle — so these limiters are not about
	// server cost. They are what bounds issuance: the endpoint is
	// unauthenticated by definition and mints a bearer for anyone who asks,
	// and with the per-IP identity cap gone they and proof-of-work are the
	// only things in the way. The request IP is all we have to key on. There
	// is no userId bucket: the body is attacker-controlled, so keying on it
	// would just make the limit free to evade.
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
		buildMetricsMiddleware("auth-anonymous-login"),
		NewReportingMetaMiddleware("auth-anonymous-login"),
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

		// Required, not merely accepted: the content type is what keeps
		// this endpoint off the CORS "simple request" path. A POST with
		// text/plain (or no Content-Type at all) carrying a JSON body is
		// dispatched cross-origin without a preflight, so any page on any
		// origin could make a visitor's browser mint sessions from the
		// visitor's IP — spending the login limiter's budget for that IP
		// and locking the real client out. The attacker can't read the
		// response, but it doesn't need to. Requiring application/json
		// forces the preflight, which BuildCORSMiddleware answers only
		// for allowed origins.
		//
		// Refresh needs no equivalent: its Authorization header is not a
		// CORS-safelisted request header, so it is always preflighted.
		if !hasJSONContentType(r) {
			logging.FromContext(ctx).InfoContext(ctx, "Rejected anonymous login with non-JSON content type",
				slog.String("contentType", r.Header.Get("Content-Type")),
			)
			http.Error(w, "Content-Type must be application/json", http.StatusUnsupportedMediaType)
			return
		}

		var body anonymousLoginRequest
		if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, authBodyMaxBytes)).Decode(&body); err != nil {
			logging.FromContext(ctx).InfoContext(ctx, "Failed to decode anonymous login body", "error", err.Error())
			http.Error(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		if !validAnonymousUserID(body.UserID) {
			http.Error(w, "Invalid userId", http.StatusBadRequest)
			return
		}

		if body.Challenge == "" || len(body.Challenge) > challengeMaxLength {
			http.Error(w, "Invalid challenge", http.StatusBadRequest)
			return
		}
		// A non-empty solution is required even though at difficulty 0 the
		// empty string is a perfectly valid proof. Accepting it would let a
		// client ship a stub that never implements the hash loop, and
		// discovering that the day we raise the difficulty is exactly the
		// retrofit this whole mechanism exists to avoid.
		if body.Solution == "" || len(body.Solution) > solutionMaxLength {
			http.Error(w, "Invalid solution", http.StatusBadRequest)
			return
		}

		logging.FromContext(ctx).InfoContext(ctx, "Handling auth-anonymous-login request",
			slog.String("bodyUserId", body.UserID),
		)

		ipHash := GetIP(r).Hash()

		// Ahead of issuing anything, which is the entire point: a proof
		// checked after the handle is sealed gates nothing. Nothing below
		// touches a database any more, so this is no longer about saving
		// server work — it is about the client paying before we mint.
		// Verification itself is one HMAC, one hash and a map lookup.
		challenge, err := parseChallenge(body.Challenge)
		if err != nil {
			// Nothing to sample: a blob we didn't sign, can't read, or whose
			// scheme we can't evaluate carries no age or difficulty we could
			// interpret.
			rejectProofOfWork(ctx, w, r, err)
			return
		}

		checkErr := challenge.Check(body.Solution, body.UserID, ipHash)

		outcome := powOutcomeAccepted
		if checkErr != nil {
			outcome = proofofwork.RejectionReason(checkErr)
		}
		recordPowChallengeAge(ctx, r, challenge, outcome)

		if checkErr != nil {
			rejectProofOfWork(ctx, w, r, checkErr)
			return
		}

		sess, err := login(ctx, body.UserID, ipHash)
		switch {
		case errors.Is(err, domain.ErrAuthSessionIssuanceRefused):
			// An issuance guard saying "not this one" is ordinary traffic,
			// not a fault: it must not page, and the client has to be able
			// to tell it apart from a server that broke.
			logging.FromContext(ctx).InfoContext(ctx, "Refused anonymous login issuance", "error", err.Error())
			http.Error(w, "Too many sessions issued", http.StatusTooManyRequests)
			return
		case err != nil:
			logging.FromContext(ctx).ErrorContext(ctx, "Anonymous login failed", "error", err.Error())
			reporting.Report(ctx, fmt.Errorf("anonymous login: %w", err))
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}

		writeAuthSessionResponse(ctx, w, sess, nowFunc())
	}

	return middleware(handler), stop
}
