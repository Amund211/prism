package proofofwork

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"math/bits"
	"strings"
	"time"
)

// AlgorithmSHA256LeadingZeros names the only proof-of-work scheme we issue
// today: find a solution such that SHA-256(challenge || ":" || solution)
// has at least `difficulty` leading zero bits. The name travels in the
// challenge response and clients reject values they don't recognize rather
// than guessing, which is what makes a future scheme additive instead of
// breaking.
const AlgorithmSHA256LeadingZeros = "sha256-leading-zeros-v1"

// challengeTTL is how long a minted challenge stays solvable. Short enough
// that a solved-but-unspent challenge is worth little.
//
// It is measured from minting, server-side, so the client's solve time and
// both round trips come out of it — which is what bounds the difficulty
// that is actually usable, well below MaxDifficulty. See the note there
// before turning the dial up: past a certain difficulty a client cannot
// finish inside the window, and since the TTL is checked before the work,
// it would loop solving challenges that expire under it.
const challengeTTL = 60 * time.Second

// clockSkewGrace is how far into the future a challenge may claim to have been
// minted before we call it our own clock jumping. Two revisions serve during a
// rollout and their clocks can disagree. Small on purpose: it extends the
// window in which a challenge is live, so it trades against challengeTTL.
const clockSkewGrace = 5 * time.Second

// challengeSeparator splits the encoded payload from its signature. Not in
// the base64url alphabet, so it can't occur inside either half.
const challengeSeparator = "."

// nonceLength is the size of the random per-challenge nonce. It only has
// to be wide enough that two live challenges never collide — a collision
// would let the used-nonce set reject a legitimate login.
const nonceLength = 16

// minSigningKeyLength is the smallest signing key we accept, matching the
// SHA-256 block output. Shorter keys are almost always a truncated or
// misconfigured secret rather than a deliberate choice.
const minSigningKeyLength = 32

var (
	// ErrInvalidConfig is returned at construction time, never per-request.
	ErrInvalidConfig = errors.New("invalid proof-of-work configuration")

	ErrMalformedChallenge = errors.New("malformed challenge")
	ErrBadSignature       = errors.New("bad challenge signature")
	ErrChallengeExpired   = errors.New("challenge expired")
	ErrIPMismatch         = errors.New("challenge was issued to a different ip")
	ErrNonceReplayed      = errors.New("challenge has already been used")
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

// IssueChallenge mints a challenge bound to the caller's ip hash.
// clientType must be the *normalized* client type: it is client-supplied,
// so it may only ever raise the cost, never lower it.
type IssueChallenge func(ipHash string, clientType string) (Challenge, error)

// VerifySolution checks a (challenge, solution) pair presented by a caller
// at ipHash, and consumes the challenge so it can't be presented twice.
// Every failure wraps one of the sentinel errors above; RejectionReason
// turns that into a bounded metric label.
type VerifySolution func(challenge string, solution string, ipHash string) error

// challengePayload is the signed half of a challenge. It is the server
// talking to itself — the client never reads it — so it carries everything
// verification needs, difficulty included. That is what lets difficulty
// vary per request without the server remembering what it asked for.
type challengePayload struct {
	Nonce  string `json:"nonce"`
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

// ParseSigningKeys decodes base64 signing keys from config. The first key
// signs every challenge we mint and all of them are accepted on the way
// back in, so rotation is: prepend the new key, deploy, drop the old one a
// TTL later. Blank entries are skipped — the config format is
// newline-delimited and gets edited by hand.
func ParseSigningKeys(encoded []string) ([][]byte, error) {
	keys := make([][]byte, 0, len(encoded))
	for i, raw := range encoded {
		raw = strings.TrimSpace(raw)
		if raw == "" {
			continue
		}
		key, err := base64.StdEncoding.DecodeString(raw)
		if err != nil {
			// Deliberately not wrapping the decode error: it quotes the
			// input, and the input is key material.
			return nil, fmt.Errorf("%w: signing key %d is not valid base64", ErrInvalidConfig, i)
		}
		if len(key) < minSigningKeyLength {
			return nil, fmt.Errorf("%w: signing key %d is %d bytes, want at least %d", ErrInvalidConfig, i, len(key), minSigningKeyLength)
		}
		keys = append(keys, key)
	}
	if len(keys) == 0 {
		return nil, fmt.Errorf("%w: no signing keys", ErrInvalidConfig)
	}
	return keys, nil
}

// GenerateSigningKey returns a fresh base64-encoded signing key.
// Development only. A key generated at startup dies with the process,
// which invalidates every outstanding challenge on restart — a 60-second
// window that a local client just retries through, but not something to
// run in production, where the key is a secret so that it also survives a
// revision rollout.
func GenerateSigningKey() (string, error) {
	var key [minSigningKeyLength]byte
	if _, err := rand.Read(key[:]); err != nil {
		return "", fmt.Errorf("failed to generate signing key: %w", err)
	}
	return base64.StdEncoding.EncodeToString(key[:]), nil
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

	return func(ipHash string, clientType string) (Challenge, error) {
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
			IPHash:             ipHash,
			IssuedAtUnixMillis: nowFunc().UnixMilli(),
			Difficulty:         difficulty,
			Algorithm:          AlgorithmSHA256LeadingZeros,
		})
		if err != nil {
			return Challenge{}, fmt.Errorf("failed to marshal challenge payload: %w", err)
		}

		body := base64.RawURLEncoding.EncodeToString(payload)
		signature := base64.RawURLEncoding.EncodeToString(sign(signingKey, body))

		return Challenge{
			Value:      body + challengeSeparator + signature,
			Algorithm:  AlgorithmSHA256LeadingZeros,
			Difficulty: difficulty,
			ExpiresIn:  challengeTTL,
		}, nil
	}, nil
}

// BuildVerifySolution returns the verifying half of the scheme. The order
// of the checks is the point of the whole mechanism and is load-bearing:
// everything here is cheap, stateless and runs ahead of any database work
// on the login path, because a proof checked after the write buys nothing.
func BuildVerifySolution(keys [][]byte, nonces UsedNonceStore, nowFunc func() time.Time) (VerifySolution, error) {
	if len(keys) == 0 {
		return nil, fmt.Errorf("%w: no signing keys", ErrInvalidConfig)
	}
	if nonces == nil {
		return nil, fmt.Errorf("%w: no used-nonce store", ErrInvalidConfig)
	}

	return func(challenge string, solution string, ipHash string) error {
		body, signature, ok := strings.Cut(challenge, challengeSeparator)
		if !ok {
			return fmt.Errorf("%w: expected two %q-separated parts", ErrMalformedChallenge, challengeSeparator)
		}
		rawSignature, err := base64.RawURLEncoding.DecodeString(signature)
		if err != nil {
			return fmt.Errorf("%w: signature is not base64url", ErrMalformedChallenge)
		}

		// The signature covers the encoded payload exactly as it arrived,
		// so verification never depends on re-encoding the payload the same
		// way we did when minting it.
		if !signedByAnyKey(keys, body, rawSignature) {
			return ErrBadSignature
		}

		rawPayload, err := base64.RawURLEncoding.DecodeString(body)
		if err != nil {
			return fmt.Errorf("%w: payload is not base64url", ErrMalformedChallenge)
		}
		var payload challengePayload
		if err := json.Unmarshal(rawPayload, &payload); err != nil {
			return fmt.Errorf("%w: payload is not json", ErrMalformedChallenge)
		}
		// Both decodes are unreachable for a blob we signed ourselves, but a
		// signature check is not a parse and shouldn't be treated as one.

		// Ahead of the nonce claim, so a challenge this revision cannot check
		// isn't also spent by it.
		if payload.Algorithm != AlgorithmSHA256LeadingZeros {
			return fmt.Errorf("%w: %q", ErrUnsupportedAlgorithm, payload.Algorithm)
		}

		// A challenge from further in the future than the skew grace is our own
		// clock jumping, not anything the caller did. Rejecting is
		// self-healing: the client just asks for another.
		age := nowFunc().Sub(time.UnixMilli(payload.IssuedAtUnixMillis))
		if age < -clockSkewGrace || age > challengeTTL {
			return ErrChallengeExpired
		}

		// Binding to the ip hash is what stops one rented CPU box solving
		// challenges on behalf of a hundred proxy exits.
		if payload.IPHash != ipHash {
			return ErrIPMismatch
		}

		// Spend the challenge before checking the work, not after: this is
		// the only state in an otherwise stateless scheme, and without it
		// one solved challenge mints sessions until it expires, which
		// prices identity per minute instead of per identity. The cost is
		// that a wrong solution burns the challenge, which is correct — the
		// client asks for a new one.
		if !nonces.Claim(payload.Nonce) {
			return ErrNonceReplayed
		}

		digest := sha256.Sum256([]byte(challenge + ":" + solution))
		if leadingZeroBits(digest) < payload.Difficulty {
			return ErrInsufficientWork
		}

		return nil
	}, nil
}

// RejectionReason maps a VerifySolution error to a bounded label safe to
// use as a metric attribute. A dial with no gauge isn't tunable, and the
// split by cause is what tells a difficulty change apart from a client
// bug.
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
	case errors.Is(err, ErrNonceReplayed):
		return "replayed"
	case errors.Is(err, ErrInsufficientWork):
		return "insufficient_work"
	case errors.Is(err, ErrUnsupportedAlgorithm):
		return "unsupported_algorithm"
	default:
		return "other"
	}
}

func signedByAnyKey(keys [][]byte, body string, signature []byte) bool {
	for _, key := range keys {
		if hmac.Equal(sign(key, body), signature) {
			return true
		}
	}
	return false
}

func sign(key []byte, body string) []byte {
	mac := hmac.New(sha256.New, key)
	// hash.Hash.Write never returns an error.
	_, _ = mac.Write([]byte(body))
	return mac.Sum(nil)
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
