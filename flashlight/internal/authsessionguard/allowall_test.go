package authsessionguard_test

import (
	"context"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/authsessionguard"
	"github.com/Amund211/flashlight/internal/domain"
)

// The no-op is the whole behaviour, and it is a decision rather than a
// stub — see the type's doc comment. Pinned so that making it refuse
// something is a deliberate edit to a failing test.
func TestAllowAllAllowsEverything(t *testing.T) {
	t.Parallel()

	ctx := context.Background()
	guard := authsessionguard.AllowAll{}

	require.NoError(t, guard.Allow(ctx, domain.AuthSessionIdentityAnonymous, "user-A", "iphash-A", time.Now()))
	require.NoError(t, guard.Allow(ctx, domain.AuthSessionIdentityAnonymous, "", "", time.Time{}))
	require.NoError(t, guard.Allow(ctx, "some-future-tier", "user-A", "iphash-A", time.Now()),
		"the guard is tier-agnostic: it does not validate the tier")
}
