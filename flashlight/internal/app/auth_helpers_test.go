package app_test

import (
	"context"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/authsessiontoken"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/signing"
)

// Local mirrors of the production tier-agnostic tunables. Kept in
// lockstep manually: if you change a value in auth_session.go, change
// it here too. We duplicate rather than export to keep the production
// package's surface internal — these values are policy, not API.
const (
	authSessionTTL    = 1 * time.Hour
	authRefreshWindow = 2 * time.Hour
	authMaxSessionAge = 24 * time.Hour
)

func fixedNow(now time.Time) func() time.Time {
	return func() time.Time { return now }
}

// fakeSessionSealer is a function-field stub satisfying the app package's
// unexported sessionSealer by structural typing. Each test wires up only
// the methods it expects to be called; an unconfigured method panics with
// a nil-pointer dereference, which is the signal that the use case touched
// a method the test didn't expect.
type fakeSessionSealer struct {
	sealFn   func(ctx context.Context, sess domain.AuthSession) (domain.AuthSession, error)
	unsealFn func(ctx context.Context, handle string) (domain.AuthSession, error)
}

func (f *fakeSessionSealer) Seal(ctx context.Context, sess domain.AuthSession) (domain.AuthSession, error) {
	return f.sealFn(ctx, sess)
}

func (f *fakeSessionSealer) Unseal(ctx context.Context, handle string) (domain.AuthSession, error) {
	return f.unsealFn(ctx, handle)
}

// newTestSealer is the real signed sealer under an all-zero key, for the
// cases that must go through the production format rather than a fake.
func newTestSealer(t *testing.T) authsessiontoken.Signed {
	t.Helper()
	sealer, err := authsessiontoken.NewSigned([][]byte{make([]byte, signing.MinKeyLength)})
	require.NoError(t, err)
	return sealer
}

// unsealTo returns a sealer whose Unseal always yields sess, and whose Seal
// hands back what it was given under a fixed handle.
func unsealTo(sess domain.AuthSession) *fakeSessionSealer {
	return &fakeSessionSealer{
		unsealFn: func(_ context.Context, _ string) (domain.AuthSession, error) {
			return sess, nil
		},
		sealFn: func(_ context.Context, s domain.AuthSession) (domain.AuthSession, error) {
			s.ID = "flsess_resealed"
			return s, nil
		},
	}
}
