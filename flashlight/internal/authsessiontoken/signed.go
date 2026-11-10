// Package authsessiontoken seals a session into a signed, stateless
// handle and unseals it again. No storage, no clock: freshness is policy
// and lives in internal/app.
package authsessiontoken

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/signing"
)

// typeV1 is the format version. Exactly one accepted value, never a set,
// so a future field change is a refusal rather than a misparse. A bump is
// staged like a key rotation: accept both, deploy; mint the new one,
// deploy; drop the old no sooner than 24h (authMaxSessionAge) later.
const typeV1 = "flsess/1"

// handlePrefix is inside the signed string, which buys three things: a
// prefix-less blob cannot verify, so TrimPrefix is never a security check;
// a challenge blob cannot verify here even if someone hands us the
// challenge key list; and the prefix cannot change without a mass logout,
// which is fine because nothing wants to change it — released rainbow
// throws on a login response without it.
const handlePrefix = "flsess_"

// handleSeparator is not in the base64url alphabet, so it cannot occur
// inside either half.
const handleSeparator = "."

// HandleMaxLength bounds the work before we do the work. The worst case
// Seal can produce is 1147 chars (a 100-char identityKey of '<', which
// encoding/json escapes to six bytes each); the headroom covers a field or
// two being added later. Pinned by
// TestHandleMaxLengthCoversEverythingSealCanProduce.
const HandleMaxLength = 1280

// payload is the signed half. Field names are spelled out rather than
// abbreviated: ~60 bytes is not worth the opacity.
type payload struct {
	Typ                       string `json:"typ"`
	IdentityType              string `json:"identityType"`
	IdentityKey               string `json:"identityKey"`
	IssuedAtUnixMillis        int64  `json:"issuedAtUnixMillis"`
	LineageIssuedAtUnixMillis int64  `json:"lineageIssuedAtUnixMillis"`
	Lineage                   string `json:"lineage"`
	Generation                int    `json:"generation"`
}

// Signed is the only sessionSealer implementation. Seal marshals and HMACs;
// Unseal verifies and unmarshals.
type Signed struct {
	keys [][]byte
}

// NewSigned takes the AUTH_SESSION_SIGNING_KEYS list — its own, never the
// challenge keys.
//
// The length check duplicates signing.ParseKeys deliberately. Every
// stateless session in the deployment rests on keys[0], so a caller that
// decoded the env var itself, or a staging value that got truncated, would
// otherwise sign everything with a brute-forceable key and nothing would
// fail. It uses the shared constant, so there is nothing to drift.
func NewSigned(keys [][]byte) (Signed, error) {
	if len(keys) == 0 {
		return Signed{}, fmt.Errorf("%w: no auth session signing keys", signing.ErrInvalidConfig)
	}
	for i, key := range keys {
		if len(key) < signing.MinKeyLength {
			return Signed{}, fmt.Errorf("%w: auth session signing key %d is %d bytes, want at least %d", signing.ErrInvalidConfig, i, len(key), signing.MinKeyLength)
		}
	}
	return Signed{keys: keys}, nil
}

// Seal returns sess with ID set to flsess_<body>.<signature>, everything
// else untouched. Deterministic: there is no per-handle nonce, so two
// reseals of one parent in the same millisecond are byte-identical.
//
// It refuses anything Unseal would, so a mint-time mistake is an error
// where it happens rather than a 200 handing the client a handle that
// then 401s on every request.
func (s Signed) Seal(_ context.Context, sess domain.AuthSession) (domain.AuthSession, error) {
	if !sess.IdentityType.IsKnown() {
		return domain.AuthSession{}, fmt.Errorf("refusing to seal unknown tier %q", sess.IdentityType)
	}
	// Not folded into the Unseal check below: a zero time's UnixMilli is a
	// large negative, not 0, so the payload would round-trip as a session
	// that started in year 1 and only fail two layers away.
	if sess.CreatedAt.IsZero() || sess.LineageIssuedAt.IsZero() {
		return domain.AuthSession{}, fmt.Errorf("refusing to seal a session missing an origin timestamp")
	}

	raw, err := json.Marshal(payload{
		Typ:                       typeV1,
		IdentityType:              string(sess.IdentityType),
		IdentityKey:               sess.IdentityKey,
		IssuedAtUnixMillis:        sess.CreatedAt.UnixMilli(),
		LineageIssuedAtUnixMillis: sess.LineageIssuedAt.UnixMilli(),
		Lineage:                   sess.Lineage,
		Generation:                sess.Generation,
	})
	if err != nil {
		return domain.AuthSession{}, fmt.Errorf("failed to marshal session payload: %w", err)
	}

	signed := handlePrefix + base64.RawURLEncoding.EncodeToString(raw)
	signature := base64.RawURLEncoding.EncodeToString(signing.Sign(s.keys[0], signed))

	handle := signed + handleSeparator + signature
	// Same lesson as challengeMaxLength: a minting side that can outrun
	// the verifying side's cap hands out handles that never validate, and
	// the handshake can never complete. Today's inputs cannot reach it
	// (the test pins that); a longer identityKey on a future tier could.
	if len(handle) > HandleMaxLength {
		return domain.AuthSession{}, fmt.Errorf("refusing to seal a %d-char handle, over the %d cap", len(handle), HandleMaxLength)
	}

	sess.ID = handle
	return sess, nil
}

// Unseal recovers the session a handle names. Every refusal is
// domain.ErrAuthSessionNotFound — it is a handle we never issued, and that
// mapping is what leaves the 401 contract in internal/ports untouched. The
// reason is in the wrapped message for the log and never on the wire.
//
// Never checks the clock, and returns the derived deadline fields zero.
func (s Signed) Unseal(_ context.Context, handle string) (domain.AuthSession, error) {
	if len(handle) > HandleMaxLength {
		return domain.AuthSession{}, fmt.Errorf("%w: handle is %d chars, over the %d cap", domain.ErrAuthSessionNotFound, len(handle), HandleMaxLength)
	}

	signed, signature, ok := strings.Cut(handle, handleSeparator)
	if !ok {
		return domain.AuthSession{}, fmt.Errorf("%w: expected two %q-separated parts", domain.ErrAuthSessionNotFound, handleSeparator)
	}
	rawSignature, err := base64.RawURLEncoding.DecodeString(signature)
	if err != nil {
		return domain.AuthSession{}, fmt.Errorf("%w: signature is not base64url", domain.ErrAuthSessionNotFound)
	}

	// Verify before parsing, and over the string exactly as it arrived, so
	// verification never depends on re-encoding the payload the way Seal
	// did — and so the prefix check below is a parse, not a security check.
	if !signing.SignedByAnyKey(s.keys, signed, rawSignature) {
		return domain.AuthSession{}, fmt.Errorf("%w: no key verifies the signature", domain.ErrAuthSessionNotFound)
	}

	body, ok := strings.CutPrefix(signed, handlePrefix)
	if !ok {
		return domain.AuthSession{}, fmt.Errorf("%w: missing the %q prefix", domain.ErrAuthSessionNotFound, handlePrefix)
	}
	rawPayload, err := base64.RawURLEncoding.DecodeString(body)
	if err != nil {
		return domain.AuthSession{}, fmt.Errorf("%w: payload is not base64url", domain.ErrAuthSessionNotFound)
	}
	var p payload
	if err := json.Unmarshal(rawPayload, &p); err != nil {
		return domain.AuthSession{}, fmt.Errorf("%w: payload is not json", domain.ErrAuthSessionNotFound)
	}

	if p.Typ != typeV1 {
		return domain.AuthSession{}, fmt.Errorf("%w: unknown typ %q", domain.ErrAuthSessionNotFound, p.Typ)
	}
	identityType := domain.AuthSessionIdentityType(p.IdentityType)
	if !identityType.IsKnown() {
		return domain.AuthSession{}, fmt.Errorf("%w: unknown identityType %q", domain.ErrAuthSessionNotFound, p.IdentityType)
	}
	// Both origins are load-bearing and neither is optional, so a zero one
	// is a handle we never minted rather than a session starting in 1970.
	if p.IssuedAtUnixMillis == 0 || p.LineageIssuedAtUnixMillis == 0 {
		return domain.AuthSession{}, fmt.Errorf("%w: payload is missing an origin timestamp", domain.ErrAuthSessionNotFound)
	}

	return domain.AuthSession{
		ID:              handle,
		IdentityType:    identityType,
		IdentityKey:     p.IdentityKey,
		CreatedAt:       time.UnixMilli(p.IssuedAtUnixMillis).UTC(),
		LineageIssuedAt: time.UnixMilli(p.LineageIssuedAtUnixMillis).UTC(),
		Lineage:         p.Lineage,
		Generation:      p.Generation,
	}, nil
}
