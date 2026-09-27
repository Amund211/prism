package app

import (
	"context"
	"crypto/sha256"
	"fmt"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
)

// A stolen value and the real one both work for this long; keep it short.
const userCredentialGraceWindow = time.Minute

type credentialRotator interface {
	Find(ctx context.Context, hash []byte, now time.Time) (domain.UserCredential, error)
	Rotate(ctx context.Context, presentedHash, newHash []byte, now time.Time, grace, idleWindow time.Duration) (domain.UserCredential, error)
}

type credentialDeleter interface {
	DeleteByIdentityOf(ctx context.Context, hash []byte) (string, int, error)
}

// RecoverMicrosoftSession trades a live credential for a new Microsoft-tier
// chain and the credential's successor. transport is the client the
// credential arrived from: fl_rm is rainbow, a body is prism. The result's
// Credential is the successor's value. Makes no outbound calls. Errors
// never quote the credential.
type RecoverMicrosoftSession func(ctx context.Context, credential string, transport domain.MicrosoftClientType, ipHash string) (MicrosoftExchanged, error)

func BuildRecoverMicrosoftSession(
	credentials credentialRotator,
	sealer sessionSealer,
	guard issuanceGuard,
	nowFunc func() time.Time,
	generateLineage func() (string, error),
) RecoverMicrosoftSession {
	return func(ctx context.Context, credential string, transport domain.MicrosoftClientType, ipHash string) (MicrosoftExchanged, error) {
		now := nowFunc()
		presentedHash := sha256.Sum256([]byte(credential))

		// Checked before rotating, so a refusal does not spend the credential.
		stored, err := credentials.Find(ctx, presentedHash[:], now)
		if err != nil {
			return MicrosoftExchanged{}, fmt.Errorf("failed to find credential: %w", err)
		}
		if stored.ClientType != transport {
			return MicrosoftExchanged{}, domain.ErrUserCredentialClientMismatch
		}
		if err := guard.Allow(ctx, domain.AuthSessionIdentityMicrosoft, stored.IdentityKey, ipHash, now); err != nil {
			return MicrosoftExchanged{}, fmt.Errorf("failed to check issuance guard: %w", err)
		}

		successor, err := randomURLSafe()
		if err != nil {
			return MicrosoftExchanged{}, fmt.Errorf("failed to generate credential: %w", err)
		}
		successorHash := sha256.Sum256([]byte(successor))
		rotated, err := credentials.Rotate(ctx, presentedHash[:], successorHash[:], now, userCredentialGraceWindow, userCredentialIdleWindow)
		if err != nil {
			return MicrosoftExchanged{}, fmt.Errorf("failed to rotate credential: %w", err)
		}

		lineage, err := generateLineage()
		if err != nil {
			return MicrosoftExchanged{}, fmt.Errorf("failed to generate lineage: %w", err)
		}
		sess, err := newChain(domain.AuthSessionIdentityMicrosoft, rotated.IdentityKey, now, lineage)
		if err != nil {
			return MicrosoftExchanged{}, fmt.Errorf("failed to derive session deadlines: %w", err)
		}
		sealed, err := sealer.Seal(ctx, sess)
		if err != nil {
			return MicrosoftExchanged{}, fmt.Errorf("failed to seal microsoft session: %w", err)
		}

		return MicrosoftExchanged{Session: sealed, ClientType: rotated.ClientType, Credential: successor}, nil
	}
}

// LogoutMicrosoft deletes every credential of the identity that holds the
// presented credential, and returns that identity and the number of rows
// deleted. A stale credential works too: deleting grants nothing, and a
// victim whose credential was rotated by a thief must still reach this.
// Live sessions are not revoked. Errors never quote the credential.
type LogoutMicrosoft func(ctx context.Context, credential string) (string, int, error)

func BuildLogoutMicrosoft(credentials credentialDeleter) LogoutMicrosoft {
	return func(ctx context.Context, credential string) (string, int, error) {
		hash := sha256.Sum256([]byte(credential))
		identityKey, deleted, err := credentials.DeleteByIdentityOf(ctx, hash[:])
		if err != nil {
			return "", 0, fmt.Errorf("failed to delete credentials: %w", err)
		}
		return identityKey, deleted, nil
	}
}
