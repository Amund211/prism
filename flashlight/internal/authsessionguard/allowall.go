// Package authsessionguard holds the issuance guards consulted before a
// new session is issued.
package authsessionguard

import (
	"context"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
)

// AllowAll issues every session asked of it. It is the only implementation,
// and it exists so that "nothing bounds issuance per IP" is a named
// collaborator in main.go rather than a missing call nobody can grep for.
//
// What it gives up: authAnonymousIPCap used to soft-revoke the
// least-recently-logged-in identities once an ip_hash held 4 concurrently
// active ones. Counting identities per IP is inherently cross-handle, and
// stateless sessions are rows nobody can count — so the control is gone,
// not ported. It was scored near zero anyway: it bounded concurrently
// *active* identities, never issuance, so a fresh IP was always worth ~200
// identities for the asking. What actually bounds anonymous issuance now is
// proof-of-work (difficulty 0 today) and the login endpoint's per-IP
// limiters.
//
// Reinstating a real guard means an implementation that can count — an
// issuance-events table — and this seam is what makes that a new type plus
// one line in main.go instead of a rewiring.
type AllowAll struct{}

func (AllowAll) Allow(
	_ context.Context,
	_ domain.AuthSessionIdentityType,
	_ string,
	_ string,
	_ time.Time,
) error {
	return nil
}
