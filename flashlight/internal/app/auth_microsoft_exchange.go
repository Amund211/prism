package app

import (
	"context"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"fmt"
	"strings"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
)

// userCredentialIdleWindow is how long an unused credential lives. It
// slides on every recover and has no absolute cap.
const userCredentialIdleWindow = 90 * 24 * time.Hour

// resultUnsealer reads the result token /exchange is handed.
type resultUnsealer interface {
	Unseal(value string) (domain.MicrosoftSignInResult, error)
}

// credentialRepository stores recovery credentials.
type credentialRepository interface {
	Insert(ctx context.Context, cred domain.UserCredential) error
}

// MicrosoftExchanged is what /exchange hands the client.
type MicrosoftExchanged struct {
	Session    domain.AuthSession
	ClientType domain.MicrosoftClientType
	// Credential is the new recovery credential's value: rainbow's fl_rm
	// cookie, prism's stored credential. Only its hash is kept.
	Credential string
}

// ExchangeMicrosoftSignIn trades a result token and the verifier behind its
// challenge for a new credential and a Microsoft-tier session. A replayed
// result mints another credential for whoever holds the verifier, which
// is the client that started the flow. Errors never quote the result or
// the verifier.
type ExchangeMicrosoftSignIn func(ctx context.Context, result, verifier, ipHash string) (MicrosoftExchanged, error)

func BuildExchangeMicrosoftSignIn(
	results resultUnsealer,
	credentials credentialRepository,
	sealer sessionSealer,
	guard issuanceGuard,
	nowFunc func() time.Time,
	generateLineage func() (string, error),
) ExchangeMicrosoftSignIn {
	return func(ctx context.Context, rawResult, verifier, ipHash string) (MicrosoftExchanged, error) {
		now := nowFunc()

		result, err := results.Unseal(rawResult)
		if err != nil {
			return MicrosoftExchanged{}, fmt.Errorf("failed to unseal result: %w", err)
		}
		if !now.Before(result.ExpiresAt) {
			return MicrosoftExchanged{}, domain.ErrMicrosoftSignInResultExpired
		}
		digest := sha256.Sum256([]byte(verifier))
		if subtle.ConstantTimeCompare([]byte(base64.RawURLEncoding.EncodeToString(digest[:])), []byte(result.Challenge)) != 1 {
			return MicrosoftExchanged{}, domain.ErrMicrosoftSignInVerifierMismatch
		}

		identityKey := strings.ReplaceAll(result.Account.UUID, "-", "")
		if err := guard.Allow(ctx, domain.AuthSessionIdentityMicrosoft, identityKey, ipHash, now); err != nil {
			return MicrosoftExchanged{}, fmt.Errorf("failed to check issuance guard: %w", err)
		}

		credential, err := randomURLSafe()
		if err != nil {
			return MicrosoftExchanged{}, fmt.Errorf("failed to generate credential: %w", err)
		}
		credentialHash := sha256.Sum256([]byte(credential))
		if err := credentials.Insert(ctx, domain.UserCredential{
			Hash:        credentialHash[:],
			IdentityKey: identityKey,
			ClientType:  result.ClientType,
			CreatedAt:   now,
			ExpiresAt:   now.Add(userCredentialIdleWindow),
		}); err != nil {
			return MicrosoftExchanged{}, fmt.Errorf("failed to store credential: %w", err)
		}

		lineage, err := generateLineage()
		if err != nil {
			return MicrosoftExchanged{}, fmt.Errorf("failed to generate lineage: %w", err)
		}
		sess, err := newChain(domain.AuthSessionIdentityMicrosoft, identityKey, now, lineage)
		if err != nil {
			return MicrosoftExchanged{}, fmt.Errorf("failed to derive session deadlines: %w", err)
		}
		sealed, err := sealer.Seal(ctx, sess)
		if err != nil {
			return MicrosoftExchanged{}, fmt.Errorf("failed to seal microsoft session: %w", err)
		}

		return MicrosoftExchanged{Session: sealed, ClientType: result.ClientType, Credential: credential}, nil
	}
}
