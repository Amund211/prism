// Package authresulttoken seals the result of a Microsoft sign-in into the
// short-lived token the callback hands the client, and unseals it at
// /exchange. It shares AUTH_FLOW_SIGNING_KEYS with authflowtoken; the
// signed prefix and typ keep the two apart. No clock: expiry is checked in
// internal/app.
package authresulttoken

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/signing"
)

// typeV1 is the one accepted format version.
const typeV1 = "flresult/1"

// valuePrefix is inside the signed string, so a flow cookie, a session
// handle or a challenge can never verify as a result under the same key.
const valuePrefix = "flresult_"

const valueSeparator = "."

// valueMaxLength bounds the work before the signature check.
const valueMaxLength = 1024

type payload struct {
	Typ                 string `json:"typ"`
	UUID                string `json:"uuid"`
	Name                string `json:"name"`
	ClientType          string `json:"clientType"`
	Challenge           string `json:"challenge"`
	ExpiresAtUnixMillis int64  `json:"expiresAtUnixMillis"`
}

type Signed struct {
	keys [][]byte
}

// NewSigned takes the AUTH_FLOW_SIGNING_KEYS list, never another scheme's.
func NewSigned(keys [][]byte) (Signed, error) {
	if len(keys) == 0 {
		return Signed{}, fmt.Errorf("%w: no auth flow signing keys", signing.ErrInvalidConfig)
	}
	for i, key := range keys {
		if len(key) < signing.MinKeyLength {
			return Signed{}, fmt.Errorf("%w: auth flow signing key %d is %d bytes, want at least %d", signing.ErrInvalidConfig, i, len(key), signing.MinKeyLength)
		}
	}
	return Signed{keys: keys}, nil
}

func complete(p payload) bool {
	return p.UUID != "" && domain.MicrosoftClientType(p.ClientType).IsKnown() && p.Challenge != "" && p.ExpiresAtUnixMillis != 0
}

// Seal returns the result token for result.
func (s Signed) Seal(result domain.MicrosoftSignInResult) (string, error) {
	if result.ExpiresAt.IsZero() {
		return "", fmt.Errorf("refusing to seal a result without an expiry")
	}
	p := payload{
		Typ:                 typeV1,
		UUID:                result.Account.UUID,
		Name:                result.Account.Username,
		ClientType:          string(result.ClientType),
		Challenge:           result.Challenge,
		ExpiresAtUnixMillis: result.ExpiresAt.UnixMilli(),
	}
	if !complete(p) {
		return "", fmt.Errorf("refusing to seal an incomplete result")
	}
	raw, err := json.Marshal(p)
	if err != nil {
		return "", fmt.Errorf("failed to marshal result payload: %w", err)
	}

	signed := valuePrefix + base64.RawURLEncoding.EncodeToString(raw)
	signature := base64.RawURLEncoding.EncodeToString(signing.Sign(s.keys[0], signed))
	value := signed + valueSeparator + signature
	if len(value) > valueMaxLength {
		return "", fmt.Errorf("refusing to seal a %d-char result, over the %d cap", len(value), valueMaxLength)
	}
	return value, nil
}

// Unseal recovers the result a token holds. Every refusal wraps
// domain.ErrMicrosoftSignInResultInvalid and never quotes the value.
func (s Signed) Unseal(value string) (domain.MicrosoftSignInResult, error) {
	if len(value) > valueMaxLength {
		return domain.MicrosoftSignInResult{}, fmt.Errorf("%w: value is %d chars, over the %d cap", domain.ErrMicrosoftSignInResultInvalid, len(value), valueMaxLength)
	}
	signed, signature, ok := strings.Cut(value, valueSeparator)
	if !ok {
		return domain.MicrosoftSignInResult{}, fmt.Errorf("%w: expected two %q-separated parts", domain.ErrMicrosoftSignInResultInvalid, valueSeparator)
	}
	rawSignature, err := base64.RawURLEncoding.DecodeString(signature)
	if err != nil {
		return domain.MicrosoftSignInResult{}, fmt.Errorf("%w: signature is not base64url", domain.ErrMicrosoftSignInResultInvalid)
	}
	if !signing.SignedByAnyKey(s.keys, signed, rawSignature) {
		return domain.MicrosoftSignInResult{}, fmt.Errorf("%w: no key verifies the signature", domain.ErrMicrosoftSignInResultInvalid)
	}

	body, ok := strings.CutPrefix(signed, valuePrefix)
	if !ok {
		return domain.MicrosoftSignInResult{}, fmt.Errorf("%w: missing the %q prefix", domain.ErrMicrosoftSignInResultInvalid, valuePrefix)
	}
	rawPayload, err := base64.RawURLEncoding.DecodeString(body)
	if err != nil {
		return domain.MicrosoftSignInResult{}, fmt.Errorf("%w: payload is not base64url", domain.ErrMicrosoftSignInResultInvalid)
	}
	var p payload
	if err := json.Unmarshal(rawPayload, &p); err != nil {
		return domain.MicrosoftSignInResult{}, fmt.Errorf("%w: payload is not json", domain.ErrMicrosoftSignInResultInvalid)
	}
	if p.Typ != typeV1 {
		return domain.MicrosoftSignInResult{}, fmt.Errorf("%w: unknown typ", domain.ErrMicrosoftSignInResultInvalid)
	}
	if !complete(p) {
		return domain.MicrosoftSignInResult{}, fmt.Errorf("%w: payload is incomplete", domain.ErrMicrosoftSignInResultInvalid)
	}

	return domain.MicrosoftSignInResult{
		Account:    domain.MinecraftAccount{UUID: p.UUID, Username: p.Name},
		ClientType: domain.MicrosoftClientType(p.ClientType),
		Challenge:  p.Challenge,
		ExpiresAt:  time.UnixMilli(p.ExpiresAtUnixMillis).UTC(),
	}, nil
}
