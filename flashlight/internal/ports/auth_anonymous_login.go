package ports

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"mime"
	"net/http"
	"time"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"

	"github.com/Amund211/flashlight/internal/app"
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
// 32 chars (uuid4 hex), so 100 is comfortably above expected traffic;
// the over-length report below gives us data to tighten the cap later.
const userIDMaxLength = 100

// userIDWarnLength is the threshold above which we still accept the
// userId but log to Sentry. Anything above 50 is unexpected (matches
// the legacy header truncation point) — keep an eye on real-world
// values before deciding whether to lower the hard cap.
const userIDWarnLength = 50

// challengeMaxLength and solutionMaxLength bound the proof-of-work fields
// before we hash anything. A challenge we minted is ~250 chars; a solution
// is a counter the client incremented until the hash came out right, which
// stays short even at the sanity-ceiling difficulty. Both caps sit well
// above that so a client picking a different (still sane) solution
// encoding doesn't trip them.
const (
	challengeMaxLength = 512
	solutionMaxLength  = 128
)

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

// MakeAnonymousLoginHandler returns a handler for POST /v1/auth/anonymous/login.
// Body: { userId, challenge, solution }. Response: a fresh session payload.
func MakeAnonymousLoginHandler(
	login app.AnonymousLogin,
	verifySolution proofofwork.VerifySolution,
	nowFunc func() time.Time,
	allowedOrigins *DomainSuffixes,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
	blocklistConfig BlocklistConfig,
) (http.HandlerFunc, func()) {
	// Every login costs an IP-cap UPDATE plus a multi-statement transaction, and
	// the endpoint is unauthenticated by definition — so it is rate limited on
	// the only thing we have before doing any of that work, the request IP.
	// There is no userId bucket: the body is attacker-controlled, so keying on
	// it would just make the limit free to evade.
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
		// visitor's IP — enough to walk their ip_hash down the cap in
		// authAnonymousIPCap requests and evict their real sessions. The
		// attacker can't read the response, but it doesn't need to.
		// Requiring application/json forces the preflight, which
		// BuildCORSMiddleware answers only for allowed origins.
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

		// 2KiB comfortably fits the largest legal body — a 100-char userId,
		// a challenge blob and a solution, all capped below — with room for
		// the JSON around them.
		var body anonymousLoginRequest
		if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 2048)).Decode(&body); err != nil {
			logging.FromContext(ctx).InfoContext(ctx, "Failed to decode anonymous login body", "error", err.Error())
			http.Error(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		if body.UserID == "" || len(body.UserID) > userIDMaxLength {
			http.Error(w, "Invalid userId", http.StatusBadRequest)
			return
		}
		if len(body.UserID) > userIDWarnLength {
			reporting.Report(
				ctx,
				fmt.Errorf("anonymous login userId longer than expected: len=%d", len(body.UserID)),
			)
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

		// Ahead of every bit of database work below, which is the entire
		// point: a proof checked after the IP-cap UPDATE and the INSERT
		// prices nothing. Verification itself is one HMAC, one hash and a
		// map lookup.
		//
		// Every cause gets the same status. They differ only in what the
		// client should have done differently, and the answer is the same
		// for all of them — fetch a fresh challenge and try again (with
		// backoff; a client that hot-loops on 403 is a client that
		// rate-limits itself out).
		if err := verifySolution(body.Challenge, body.Solution, ipHash); err != nil {
			reason := proofofwork.RejectionReason(err)
			logging.FromContext(ctx).InfoContext(ctx, "Rejected anonymous login proof of work",
				slog.String("reason", reason),
				slog.String("error", err.Error()),
			)
			metrics.powRejectedLoginCount.Add(ctx, 1, metric.WithAttributes(
				append(GetClient(r).MetricAttributes(), attribute.String("reason", reason))...,
			))
			http.Error(w, "Invalid proof of work", http.StatusForbidden)
			return
		}

		sess, err := login(ctx, body.UserID, ipHash)
		if err != nil {
			logging.FromContext(ctx).ErrorContext(ctx, "Anonymous login failed", "error", err.Error())
			reporting.Report(ctx, fmt.Errorf("anonymous login: %w", err))
			http.Error(w, "Internal server error", http.StatusInternalServerError)
			return
		}

		writeAuthSessionResponse(ctx, w, sess, nowFunc())
	}

	return middleware(handler), stop
}
