package app

import (
	"context"
	"fmt"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
)

// RefreshSession extends the lifetime of an existing session given its
// bearer handle. Accepts handles that are past expiry but still within
// the refresh window and the max-age cap.
type RefreshSession func(ctx context.Context, sessionID string, ipHash string) (domain.AuthSession, error)

// BuildRefreshSession refreshes against a sessionSealer: unseal, apply
// refreshed(), seal a *new* handle. Nothing mutates, so there is no cache
// entry to invalidate — which is what this whole backing was for.
//
// ipHash is ignored — it is not in the signed payload, since a copy baked
// into a token is stale by definition and roaming clients make it wrong
// rather than merely old. The parameter stays so the wire contract and
// ports are untouched.
func BuildRefreshSession(sealer sessionSealer, nowFunc func() time.Time) RefreshSession {
	return func(ctx context.Context, handle string, _ string) (domain.AuthSession, error) {
		sess, err := sealer.Unseal(ctx, handle)
		if err != nil {
			return domain.AuthSession{}, fmt.Errorf("failed to refresh session: %w", err)
		}

		next, err := refreshed(sess, nowFunc())
		if err != nil {
			return domain.AuthSession{}, fmt.Errorf("failed to refresh session: %w", err)
		}

		sealed, err := sealer.Seal(ctx, next)
		if err != nil {
			return domain.AuthSession{}, fmt.Errorf("failed to refresh session: %w", err)
		}
		return sealed, nil
	}
}
