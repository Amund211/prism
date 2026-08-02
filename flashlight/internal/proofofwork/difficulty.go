package proofofwork

import "fmt"

// MaxDifficulty is the absolute ceiling on the work we will ever ask a
// client for. Clients are expected to honour any difficulty up to this and
// to surface an error above it, so a server-side bug can't wedge an overlay
// in a hash loop. Enforced at mint time regardless of what the difficulty
// function returns.
//
// It is a refusal threshold, not a usable setting. 2^26 expected hashes is
// well over a minute in prism's Python client, and challengeTTL gives the
// whole handshake 60 seconds — so a difficulty near this ceiling doesn't
// converge at all: the client solves, gets ErrChallengeExpired (the TTL is
// checked before the work), fetches another and repeats. The band that
// actually works is roughly up to 22; anything beyond that needs
// challengeTTL raised in the same change.
const MaxDifficulty = 26

// DefaultDifficulty is where the dial sits normally. Zero: the mechanism
// ships mandatory and the work ships at nothing, so raising the price of
// an anonymous identity later needs no client release.
const DefaultDifficulty = 0

// DifficultyInput is everything the difficulty policy may key on. All of
// it is knowable server-side at challenge time, which is the point —
// nothing about the dial should need a client release.
type DifficultyInput struct {
	// IPHash is the sha256 of the caller's IP.
	IPHash string
	// ClientType is the *normalized* client type (ports.Client.Type), not
	// the raw header. It is client-supplied either way, so it may only ever
	// raise the cost, never lower it below the global floor.
	ClientType string
}

// DifficultyFunc is evaluated once per minted challenge. A function rather
// than a constant on purpose: per-IP issuance volume, blocklist state and
// global load are all things we'd want to price in without shipping
// anything to clients.
type DifficultyFunc func(DifficultyInput) int

// BuildDifficultyFunc returns the difficulty policy. Today every caller
// gets the global floor: the signals worth escalating on want real
// issuance-per-IP data to calibrate against, and there is no live client
// producing any yet. They plug in here, and they may only raise the number
// — BuildIssueChallenge clamps the result to MaxDifficulty.
func BuildDifficultyFunc(globalFloor int) (DifficultyFunc, error) {
	if globalFloor < 0 || globalFloor > MaxDifficulty {
		return nil, fmt.Errorf("%w: difficulty floor %d is outside [0, %d]", ErrInvalidConfig, globalFloor, MaxDifficulty)
	}
	return func(in DifficultyInput) int {
		return globalFloor
	}, nil
}
