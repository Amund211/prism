package app

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"fmt"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
)

// microsoftSignInFlowTTL bounds a sign-in from /start to /callback. It is
// also the cookie's Max-Age and how long a dropped flow key matters.
const microsoftSignInFlowTTL = 10 * time.Minute

// microsoftSignIn is the Microsoft → Minecraft chain.
type microsoftSignIn interface {
	AuthorizeURL(state, codeChallenge string) string
	SignIn(ctx context.Context, code, codeVerifier string) (domain.MinecraftAccount, error)
}

// flowSealer seals a flow into the flow cookie's value and back.
type flowSealer interface {
	Seal(flow domain.MicrosoftSignInFlow) (string, error)
	Unseal(value string) (domain.MicrosoftSignInFlow, error)
}

// MicrosoftSignInStart is what /start hands the browser.
type MicrosoftSignInStart struct {
	AuthorizeURL string
	// FlowCookie is the signed flow cookie's value.
	FlowCookie string
	ExpiresIn  time.Duration
}

// StartMicrosoftSignIn begins a flow: a fresh state and PKCE verifier,
// sealed into the flow cookie, and the Microsoft authorize URL.
type StartMicrosoftSignIn func(ctx context.Context) (MicrosoftSignInStart, error)

func BuildStartMicrosoftSignIn(microsoft microsoftSignIn, sealer flowSealer, nowFunc func() time.Time) StartMicrosoftSignIn {
	return func(ctx context.Context) (MicrosoftSignInStart, error) {
		state, err := randomURLSafe()
		if err != nil {
			return MicrosoftSignInStart{}, fmt.Errorf("failed to generate state: %w", err)
		}
		verifier, err := randomURLSafe()
		if err != nil {
			return MicrosoftSignInStart{}, fmt.Errorf("failed to generate PKCE verifier: %w", err)
		}

		cookie, err := sealer.Seal(domain.MicrosoftSignInFlow{
			State:     state,
			Verifier:  verifier,
			ExpiresAt: nowFunc().Add(microsoftSignInFlowTTL),
		})
		if err != nil {
			return MicrosoftSignInStart{}, fmt.Errorf("failed to seal flow: %w", err)
		}

		challenge := sha256.Sum256([]byte(verifier))
		return MicrosoftSignInStart{
			AuthorizeURL: microsoft.AuthorizeURL(state, base64.RawURLEncoding.EncodeToString(challenge[:])),
			FlowCookie:   cookie,
			ExpiresIn:    microsoftSignInFlowTTL,
		}, nil
	}
}

// FinishMicrosoftSignIn verifies the flow cookie and state, then redeems
// code and runs the chain. flowCookie is "" when the browser sent none.
// Errors never quote the cookie, state or code.
type FinishMicrosoftSignIn func(ctx context.Context, flowCookie, state, code string) (domain.MinecraftAccount, error)

func BuildFinishMicrosoftSignIn(microsoft microsoftSignIn, sealer flowSealer, nowFunc func() time.Time) FinishMicrosoftSignIn {
	return func(ctx context.Context, flowCookie, state, code string) (domain.MinecraftAccount, error) {
		if flowCookie == "" {
			return domain.MinecraftAccount{}, domain.ErrMicrosoftSignInFlowMissing
		}
		flow, err := sealer.Unseal(flowCookie)
		if err != nil {
			return domain.MinecraftAccount{}, fmt.Errorf("failed to unseal flow: %w", err)
		}
		if !nowFunc().Before(flow.ExpiresAt) {
			return domain.MinecraftAccount{}, domain.ErrMicrosoftSignInFlowExpired
		}
		if subtle.ConstantTimeCompare([]byte(state), []byte(flow.State)) != 1 {
			return domain.MinecraftAccount{}, domain.ErrMicrosoftSignInStateMismatch
		}

		account, err := microsoft.SignIn(ctx, code, flow.Verifier)
		if err != nil {
			return domain.MinecraftAccount{}, fmt.Errorf("failed to sign in: %w", err)
		}
		return account, nil
	}
}

// randomURLSafe returns 32 random bytes as base64url: 43 chars, which is
// also the RFC 7636 minimum for a verifier.
func randomURLSafe() (string, error) {
	var b [32]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(b[:]), nil
}
