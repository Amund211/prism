package proofofwork

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"math/bits"
	"strings"
	"time"

	"github.com/Amund211/flashlight/internal/signing"
)

// AlgorithmSHA256LeadingZeros names the only proof-of-work scheme we issue
// today: find a solution such that SHA-256(challenge || ":" || solution)
// has at least `difficulty` leading zero bits. The name travels in the
// challenge response and clients reject values they don't recognize rather
// than guessing, which is what makes a future scheme additive instead of
// breaking.
const AlgorithmSHA256LeadingZeros = "sha256-leading-zeros-v1"

// challengeTTL is how long a minted challenge stays solvable.
//
// It is measured from minting, server-side, so the client's solve time and
// both round trips come out of it — which is what bounds the difficulty
// that is actually usable, well below MaxDifficulty. See the note there
// before turning the dial up: past a certain difficulty a client cannot
// finish inside the window, and since the TTL is checked before the work,
// it would loop solving challenges that expire under it.
//
// It is also the replay window, and that is the whole bound on replay: a
// solved challenge logs in as often as the login limiter allows until it
// expires. Those two roles pull in opposite directions — a higher
// difficulty wants a longer TTL, a shorter TTL is what keeps replay cheap
// to ignore — so neither can be retuned without the other in mind.
const challengeTTL = 60 * time.Second

// clockSkewGrace is how far into the future a challenge may claim to have been
// minted before we call it our own clock jumping. Two revisions serve during a
// rollout and their clocks can disagree. Small on purpose: it extends the
// window in which a challenge is live, so it trades against challengeTTL.
const clockSkewGrace = 5 * time.Second

// challengeSeparator splits the encoded payload from its signature. Not in
// the base64url alphabet, so it can't occur inside either half.
const challengeSeparator = "."

// nonceLength is the size of the random per-challenge nonce, which is what
// makes two challenges minted for the same caller in the same millisecond
// distinct and unpredictable.
const nonceLength = 16

var (
	// ErrInvalidConfig is returned at construction time, never per-request.
	// Key material is validated by internal/signing and reports
	// signing.ErrInvalidConfig; this one covers this package's own wiring.
	ErrInvalidConfig = errors.New("invalid proof-of-work configuration")

	ErrMalformedChallenge = errors.New("malformed challenge")
	ErrBadSignature       = errors.New("bad challenge signature")
	ErrChallengeExpired   = errors.New("challenge expired")
	ErrIPMismatch         = errors.New("challenge was issued to a different ip")
	ErrUserIDMismatch     = errors.New("challenge was issued to a different user id")
	ErrInsufficientWork   = errors.New("solution does not meet the required difficulty")

	// ErrUnsupportedAlgorithm means we signed it but cannot check it: a newer
	// revision minted it under a scheme this one doesn't implement.
	ErrUnsupportedAlgorithm = errors.New("challenge uses an unsupported algorithm")
)

// Challenge is a minted proof-of-work challenge, ready to be handed to a
// client. Value is opaque to the client; everything the client needs in
// order to solve it is spelled out in the other fields.
type Challenge struct {
	Value      string
	Algorithm  string
	Difficulty int
	ExpiresIn  time.Duration
}

// IssueChallenge mints a challenge bound to the userId the caller intends
// to log in as and to their ip hash. clientType must be the *normalized*
// client type: it is client-supplied, so it may only ever raise the cost,
// never lower it.
type IssueChallenge func(userID string, ipHash string, clientType string) (Challenge, error)

// ParseChallenge recovers a challenge we minted from the blob a client
// presents. Every check it makes is a pure function of that blob, so a value
// coming back carries observations that hold however the verdict goes, and a
// failure means there was nothing to observe. Anything reading the clock or
// caller input is on SignedChallenge.Check.
type ParseChallenge func(challenge string) (SignedChallenge, error)

// SignedChallenge is a challenge signed by one of our keys, naming a scheme
// we implement. Not a verdict on the caller's solution — that is Check.
//
// An interface only so callers can fake it; nothing outside this package can
// build one.
type SignedChallenge interface {
	// Difficulty is read from the signed payload, never re-derived: the dial
	// can move between mint and login, so re-deriving would report a
	// difficulty the client was never asked for.
	Difficulty() int

	// Age is minted-until-now, so it spans both round trips and the client's
	// own solve. Negative when our clock stepped backwards, and unbounded
	// above once past challengeTTL.
	Age() time.Duration

	// Check verifies freshness, the bindings and the work. Every failure
	// wraps one of the sentinel errors above.
	//
	// userID must be the raw value that becomes the session's identity_key,
	// compared byte for byte against what was minted. Normalizing on one
	// side only would reject correct solutions.
	Check(solution string, userID string, ipHash string) error
}

type signedChallenge struct {
	// raw is the blob as it arrived; the digest is taken over it, so it must
	// not be rebuilt from payload.
	raw     string
	payload challengePayload
	nowFunc func() time.Time
}

// challengePayload is the signed half of a challenge. It is the server
// talking to itself — the client never reads it — so it carries everything
// verification needs, difficulty included. That is what lets difficulty
// vary per request without the server remembering what it asked for.
type challengePayload struct {
	Nonce string `json:"nonce"`
	// UserID is what makes replay harmless and the used-nonce set
	// unnecessary: a reused solution mints sessions for one identity, which
	// shares one budget, and is the multiple-tabs case we already allow.
	UserID string `json:"userId"`
	IPHash string `json:"ipHash"`
	// Milliseconds because the age of a challenge is a measurement: truncating
	// the mint instant to a whole second would add a second of noise to it,
	// which is several times a difficulty-0 round trip.
	IssuedAtUnixMillis int64 `json:"issuedAtUnixMillis"`
	Difficulty         int   `json:"difficulty"`
	// Signed for the same reason difficulty is, so verification never assumes
	// which scheme was asked for. Clients reject an algorithm they don't
	// recognize; this is the server holding up the same end.
	Algorithm string `json:"alg"`
}

// BuildIssueChallenge returns the challenge minting half of the scheme.
func BuildIssueChallenge(keys [][]byte, difficultyFor DifficultyFunc, nowFunc func() time.Time) (IssueChallenge, error) {
	if len(keys) == 0 {
		return nil, fmt.Errorf("%w: no signing keys", ErrInvalidConfig)
	}
	if difficultyFor == nil {
		return nil, fmt.Errorf("%w: no difficulty function", ErrInvalidConfig)
	}
	signingKey := keys[0]

	return func(userID string, ipHash string, clientType string) (Challenge, error) {
		var nonce [nonceLength]byte
		if _, err := rand.Read(nonce[:]); err != nil {
			return Challenge{}, fmt.Errorf("failed to generate challenge nonce: %w", err)
		}

		// The sanity ceiling is enforced here, at the one point where a
		// difficulty enters the signed blob: whatever signals get wired
		// into difficultyFor later, a bug in one of them must not be able
		// to hand out work no real client will ever finish.
		difficulty := min(max(difficultyFor(DifficultyInput{IPHash: ipHash, ClientType: clientType}), 0), MaxDifficulty)

		payload, err := json.Marshal(challengePayload{
			Nonce:              base64.RawURLEncoding.EncodeToString(nonce[:]),
			UserID:             userID,
			IPHash:             ipHash,
			IssuedAtUnixMillis: nowFunc().UnixMilli(),
			Difficulty:         difficulty,
			Algorithm:          AlgorithmSHA256LeadingZeros,
		})
		if err != nil {
			return Challenge{}, fmt.Errorf("failed to marshal challenge payload: %w", err)
		}

		body := base64.RawURLEncoding.EncodeToString(payload)
		signature := base64.RawURLEncoding.EncodeToString(signing.Sign(signingKey, body))

		return Challenge{
			Value:      body + challengeSeparator + signature,
			Algorithm:  AlgorithmSHA256LeadingZeros,
			Difficulty: difficulty,
			ExpiresIn:  challengeTTL,
		}, nil
	}, nil
}

// BuildParseChallenge returns the parsing half of the verifying side.
func BuildParseChallenge(keys [][]byte, nowFunc func() time.Time) (ParseChallenge, error) {
	if len(keys) == 0 {
		return nil, fmt.Errorf("%w: no signing keys", ErrInvalidConfig)
	}

	return func(challenge string) (SignedChallenge, error) {
		body, signature, ok := strings.Cut(challenge, challengeSeparator)
		if !ok {
			return nil, fmt.Errorf("%w: expected two %q-separated parts", ErrMalformedChallenge, challengeSeparator)
		}
		rawSignature, err := base64.RawURLEncoding.DecodeString(signature)
		if err != nil {
			return nil, fmt.Errorf("%w: signature is not base64url", ErrMalformedChallenge)
		}

		// The signature covers the encoded payload exactly as it arrived,
		// so verification never depends on re-encoding the payload the same
		// way we did when minting it.
		if !signing.SignedByAnyKey(keys, body, rawSignature) {
			return nil, ErrBadSignature
		}

		rawPayload, err := base64.RawURLEncoding.DecodeString(body)
		if err != nil {
			return nil, fmt.Errorf("%w: payload is not base64url", ErrMalformedChallenge)
		}
		var payload challengePayload
		if err := json.Unmarshal(rawPayload, &payload); err != nil {
			return nil, fmt.Errorf("%w: payload is not json", ErrMalformedChallenge)
		}
		// Both decodes are unreachable for a blob we signed ourselves, but a
		// signature check is not a parse and shouldn't be treated as one.

		// Here rather than in Check: difficulty means nothing without the
		// scheme it was set under, so a challenge we can't evaluate is one we
		// can't observe either.
		if payload.Algorithm != AlgorithmSHA256LeadingZeros {
			return nil, fmt.Errorf("%w: %q", ErrUnsupportedAlgorithm, payload.Algorithm)
		}

		return signedChallenge{raw: challenge, payload: payload, nowFunc: nowFunc}, nil
	}, nil
}

func (c signedChallenge) Difficulty() int {
	return c.payload.Difficulty
}

func (c signedChallenge) Age() time.Duration {
	return c.nowFunc().Sub(time.UnixMilli(c.payload.IssuedAtUnixMillis))
}

// Check is cheap and stateless, and runs ahead of any database work on the
// login path, because a proof checked after the write buys nothing.
func (c signedChallenge) Check(solution string, userID string, ipHash string) error {
	// A challenge from further in the future than the skew grace is our own
	// clock jumping, not anything the caller did. Rejecting is self-healing:
	// the client just asks for another.
	age := c.Age()
	if age < -clockSkewGrace || age > challengeTTL {
		return ErrChallengeExpired
	}

	// Binding to the ip hash is what stops one rented CPU box solving
	// challenges on behalf of a hundred proxy exits.
	if c.payload.IPHash != ipHash {
		return ErrIPMismatch
	}

	// And binding to the user id is what keeps a replayed solution
	// worth nothing: it can only mint sessions for the identity it was
	// minted for, and those share that identity's budget. Cost per
	// identity — the thing the work is meant to price — is unchanged,
	// since a second identity still needs a second solve.
	if c.payload.UserID != userID {
		return ErrUserIDMismatch
	}

	digest := sha256.Sum256([]byte(c.raw + ":" + solution))
	if leadingZeroBits(digest) < c.payload.Difficulty {
		return ErrInsufficientWork
	}

	return nil
}

// RejectionReason maps an error from ParseChallenge or Check to a bounded
// label safe to use as a metric attribute. A dial with no gauge isn't
// tunable, and the split by cause is what tells a difficulty change apart
// from a client bug.
func RejectionReason(err error) string {
	switch {
	case errors.Is(err, ErrMalformedChallenge):
		return "malformed"
	case errors.Is(err, ErrBadSignature):
		return "bad_signature"
	case errors.Is(err, ErrChallengeExpired):
		return "expired"
	case errors.Is(err, ErrIPMismatch):
		return "ip_mismatch"
	case errors.Is(err, ErrUserIDMismatch):
		return "user_id_mismatch"
	case errors.Is(err, ErrInsufficientWork):
		return "insufficient_work"
	case errors.Is(err, ErrUnsupportedAlgorithm):
		return "unsupported_algorithm"
	default:
		return "other"
	}
}

func leadingZeroBits(digest [sha256.Size]byte) int {
	total := 0
	for _, b := range digest {
		total += bits.LeadingZeros8(b)
		if b != 0 {
			break
		}
	}
	return total
}
