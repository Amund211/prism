// Package authflowtoken seals a Microsoft sign-in flow into the signed value
// of the __Host-fl_flow cookie and unseals it again. Signed, not encrypted:
// the cookie is HttpOnly in the user's own browser and never reaches
// Microsoft. No clock: expiry is checked in internal/app.
package authflowtoken

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
const typeV1 = "flflow/1"

// valuePrefix is inside the signed string, so a session handle or a
// challenge can never verify as a flow even under the same key.
const valuePrefix = "flflow_"

const valueSeparator = "."

// valueMaxLength bounds the work before the signature check.
const valueMaxLength = 1024

type payload struct {
	Typ                 string `json:"typ"`
	MSState             string `json:"msState"`
	MSVerifier          string `json:"msVerifier"`
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

// Seal returns the cookie value for flow.
func (s Signed) Seal(flow domain.MicrosoftSignInFlow) (string, error) {
	if flow.State == "" || flow.Verifier == "" || flow.ExpiresAt.IsZero() {
		return "", fmt.Errorf("refusing to seal an incomplete flow")
	}
	raw, err := json.Marshal(payload{
		Typ:                 typeV1,
		MSState:             flow.State,
		MSVerifier:          flow.Verifier,
		ExpiresAtUnixMillis: flow.ExpiresAt.UnixMilli(),
	})
	if err != nil {
		return "", fmt.Errorf("failed to marshal flow payload: %w", err)
	}

	signed := valuePrefix + base64.RawURLEncoding.EncodeToString(raw)
	signature := base64.RawURLEncoding.EncodeToString(signing.Sign(s.keys[0], signed))
	value := signed + valueSeparator + signature
	if len(value) > valueMaxLength {
		return "", fmt.Errorf("refusing to seal a %d-char flow, over the %d cap", len(value), valueMaxLength)
	}
	return value, nil
}

// Unseal recovers the flow a cookie value holds. Every refusal wraps
// domain.ErrMicrosoftSignInFlowInvalid and never quotes the value.
func (s Signed) Unseal(value string) (domain.MicrosoftSignInFlow, error) {
	if len(value) > valueMaxLength {
		return domain.MicrosoftSignInFlow{}, fmt.Errorf("%w: value is %d chars, over the %d cap", domain.ErrMicrosoftSignInFlowInvalid, len(value), valueMaxLength)
	}
	signed, signature, ok := strings.Cut(value, valueSeparator)
	if !ok {
		return domain.MicrosoftSignInFlow{}, fmt.Errorf("%w: expected two %q-separated parts", domain.ErrMicrosoftSignInFlowInvalid, valueSeparator)
	}
	rawSignature, err := base64.RawURLEncoding.DecodeString(signature)
	if err != nil {
		return domain.MicrosoftSignInFlow{}, fmt.Errorf("%w: signature is not base64url", domain.ErrMicrosoftSignInFlowInvalid)
	}
	if !signing.SignedByAnyKey(s.keys, signed, rawSignature) {
		return domain.MicrosoftSignInFlow{}, fmt.Errorf("%w: no key verifies the signature", domain.ErrMicrosoftSignInFlowInvalid)
	}

	body, ok := strings.CutPrefix(signed, valuePrefix)
	if !ok {
		return domain.MicrosoftSignInFlow{}, fmt.Errorf("%w: missing the %q prefix", domain.ErrMicrosoftSignInFlowInvalid, valuePrefix)
	}
	rawPayload, err := base64.RawURLEncoding.DecodeString(body)
	if err != nil {
		return domain.MicrosoftSignInFlow{}, fmt.Errorf("%w: payload is not base64url", domain.ErrMicrosoftSignInFlowInvalid)
	}
	var p payload
	if err := json.Unmarshal(rawPayload, &p); err != nil {
		return domain.MicrosoftSignInFlow{}, fmt.Errorf("%w: payload is not json", domain.ErrMicrosoftSignInFlowInvalid)
	}
	if p.Typ != typeV1 {
		return domain.MicrosoftSignInFlow{}, fmt.Errorf("%w: unknown typ", domain.ErrMicrosoftSignInFlowInvalid)
	}
	if p.MSState == "" || p.MSVerifier == "" || p.ExpiresAtUnixMillis == 0 {
		return domain.MicrosoftSignInFlow{}, fmt.Errorf("%w: payload is incomplete", domain.ErrMicrosoftSignInFlowInvalid)
	}

	return domain.MicrosoftSignInFlow{
		State:     p.MSState,
		Verifier:  p.MSVerifier,
		ExpiresAt: time.UnixMilli(p.ExpiresAtUnixMillis).UTC(),
	}, nil
}
