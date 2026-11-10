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
// sealed into the flow cookie with target, and the Microsoft authorize
// URL. target is validated by the caller; nil is the test sign-in.
type StartMicrosoftSignIn func(ctx context.Context, target *domain.MicrosoftSignInTarget) (MicrosoftSignInStart, error)

func BuildStartMicrosoftSignIn(microsoft microsoftSignIn, sealer flowSealer, nowFunc func() time.Time) StartMicrosoftSignIn {
	return func(ctx context.Context, target *domain.MicrosoftSignInTarget) (MicrosoftSignInStart, error) {
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
			Target:    target,
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

// microsoftSignInResultTTL bounds the hop from the callback to /exchange.
const microsoftSignInResultTTL = 60 * time.Second

// resultSealer seals the result token the callback hands a client.
type resultSealer interface {
	Seal(result domain.MicrosoftSignInResult) (string, error)
}

// MicrosoftSignInFinished is the outcome of a callback.
type MicrosoftSignInFinished struct {
	Account domain.MinecraftAccount
	// Target is the flow's, set whenever the flow cookie verified — also
	// alongside an error, so a client can be sent its failure. Nil for the
	// test sign-in.
	Target *domain.MicrosoftSignInTarget
	// Result is the signed result token, set only on success with a
	// Target.
	Result string
}

// MicrosoftCallback is what Microsoft's redirect back carries.
type MicrosoftCallback struct {
	// FlowCookie is "" when the browser sent none.
	FlowCookie string
	State      string
	Code       string
	// MicrosoftRefused is set when Microsoft sent an error instead of a
	// code, for example when the user cancelled.
	MicrosoftRefused bool
}

// FinishMicrosoftSignIn verifies the flow cookie and state, then redeems
// the code and runs the chain. Errors never quote the cookie, state or
// code.
type FinishMicrosoftSignIn func(ctx context.Context, callback MicrosoftCallback) (MicrosoftSignInFinished, error)

func BuildFinishMicrosoftSignIn(microsoft microsoftSignIn, flows flowSealer, results resultSealer, nowFunc func() time.Time) FinishMicrosoftSignIn {
	return func(ctx context.Context, callback MicrosoftCallback) (MicrosoftSignInFinished, error) {
		if callback.FlowCookie == "" {
			return MicrosoftSignInFinished{}, domain.ErrMicrosoftSignInFlowMissing
		}
		flow, err := flows.Unseal(callback.FlowCookie)
		if err != nil {
			return MicrosoftSignInFinished{}, fmt.Errorf("failed to unseal flow: %w", err)
		}
		failed := MicrosoftSignInFinished{Target: flow.Target}
		if !nowFunc().Before(flow.ExpiresAt) {
			return failed, domain.ErrMicrosoftSignInFlowExpired
		}
		if subtle.ConstantTimeCompare([]byte(callback.State), []byte(flow.State)) != 1 {
			return failed, domain.ErrMicrosoftSignInStateMismatch
		}
		if callback.MicrosoftRefused {
			return failed, domain.ErrMicrosoftSignInRefused
		}

		account, err := microsoft.SignIn(ctx, callback.Code, flow.Verifier)
		if err != nil {
			return failed, fmt.Errorf("failed to sign in: %w", err)
		}
		if flow.Target == nil {
			return MicrosoftSignInFinished{Account: account}, nil
		}

		result, err := results.Seal(domain.MicrosoftSignInResult{
			Account:    account,
			ClientType: flow.Target.ClientType,
			Challenge:  flow.Target.Challenge,
			ExpiresAt:  nowFunc().Add(microsoftSignInResultTTL),
		})
		if err != nil {
			return failed, fmt.Errorf("failed to seal result: %w", err)
		}
		return MicrosoftSignInFinished{Account: account, Target: flow.Target, Result: result}, nil
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
