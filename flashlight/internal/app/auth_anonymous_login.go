package app

import (
	"context"
	"fmt"
	"time"

	"github.com/google/uuid"

	"github.com/Amund211/flashlight/internal/domain"
)

// issuanceGuard is consulted before a new session is issued. It refuses
// by returning an error wrapping domain.ErrAuthSessionIssuanceRefused —
// anything else is read as the guard itself breaking, which internal/ports
// answers with a 500 and a Sentry report rather than the 429 a refused
// client should see. Deliberately not a sessionSealer method: a backing
// that cannot count across handles has to say so at the wiring site in
// main.go, not by silently succeeding. Today the only implementation is
// authsessionguard.AllowAll, whose doc comment records what was given up.
type issuanceGuard interface {
	Allow(ctx context.Context, identityType domain.AuthSessionIdentityType, identityKey string, ipHash string, now time.Time) error
}

// AnonymousLogin issues a new anonymous-tier session for (userID,
// ipHash), if the issuance guard allows it. Nothing the caller already
// holds is touched: concurrent sessions for one identity coexist and
// expire naturally.
//
// userID is trusted as-is — input shape validation is the caller's
// responsibility.
type AnonymousLogin func(ctx context.Context, userID string, ipHash string) (domain.AuthSession, error)

// BuildAnonymousLogin starts a refresh chain: generation 0, with both
// origins at now. ipHash reaches the guard and stops there — it is not in
// the sealed payload, so nothing carries a hashed IP into a client's
// storage.
func BuildAnonymousLogin(
	sealer sessionSealer,
	guard issuanceGuard,
	nowFunc func() time.Time,
	generateLineage func() (string, error),
) AnonymousLogin {
	return func(ctx context.Context, userID string, ipHash string) (domain.AuthSession, error) {
		now := nowFunc()

		if err := guard.Allow(ctx, domain.AuthSessionIdentityAnonymous, userID, ipHash, now); err != nil {
			return domain.AuthSession{}, fmt.Errorf("failed to check issuance guard: %w", err)
		}

		lineage, err := generateLineage()
		if err != nil {
			return domain.AuthSession{}, fmt.Errorf("failed to generate lineage: %w", err)
		}

		// The one place both origins are stamped from the same instant.
		// Every reseal copies LineageIssuedAt and re-stamps CreatedAt; see
		// refreshed().
		sess, err := withDeadlines(domain.AuthSession{
			IdentityType:    domain.AuthSessionIdentityAnonymous,
			IdentityKey:     userID,
			CreatedAt:       now,
			LineageIssuedAt: now,
			Lineage:         lineage,
			Generation:      0,
		})
		if err != nil {
			return domain.AuthSession{}, fmt.Errorf("failed to derive session deadlines: %w", err)
		}

		sealed, err := sealer.Seal(ctx, sess)
		if err != nil {
			return domain.AuthSession{}, fmt.Errorf("failed to seal anonymous session: %w", err)
		}

		return sealed, nil
	}
}

// lineagePrefix tags a refresh chain's id the way sessions are tagged, so
// a lineage is recognizable at a glance in a log line and cannot be
// confused with a handle. It rides in the payload, which is signed but not
// encrypted, so anyone holding the handle can read it — never put anything
// in a lineage that a client may not see.
const lineagePrefix = "fllineage_"

// GenerateLineage mints a chain id. UUIDv7 rather than random bytes so
// the id sorts by mint time — the property an events table would want,
// and free here.
func GenerateLineage() (string, error) {
	id, err := uuid.NewV7()
	if err != nil {
		return "", fmt.Errorf("failed to generate lineage: %w", err)
	}
	return lineagePrefix + id.String(), nil
}
