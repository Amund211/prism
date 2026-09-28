package app_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
)

type listCall struct {
	identityKey string
	now         time.Time
}

type fakeSignInLister struct {
	signIns []domain.ActiveSignIn
	err     error
	calls   []listCall
}

func (f *fakeSignInLister) ListActive(_ context.Context, identityKey string, now time.Time) ([]domain.ActiveSignIn, error) {
	f.calls = append(f.calls, listCall{identityKey, now})
	return f.signIns, f.err
}

func TestListMicrosoftSignIns(t *testing.T) {
	t.Parallel()

	const identity = "a937646bf11544c38dbf9ae4a65669a0"
	listed := []domain.ActiveSignIn{{
		ClientType: domain.MicrosoftClientPrism,
		CreatedAt:  signInNow.Add(-time.Hour),
		LastUsedAt: signInNow.Add(-time.Minute),
	}}

	t.Run("lists the identity's sign-ins as of now", func(t *testing.T) {
		t.Parallel()
		lister := &fakeSignInLister{signIns: listed}
		list := app.BuildListMicrosoftSignIns(lister, func() time.Time { return signInNow })

		got, err := list(t.Context(), domain.AuthSessionIdentityMicrosoft, identity)
		require.NoError(t, err)
		require.Equal(t, listed, got)
		require.Equal(t, []listCall{{identity, signInNow}}, lister.calls)
	})

	t.Run("refuses a session of another tier without reading", func(t *testing.T) {
		t.Parallel()
		lister := &fakeSignInLister{signIns: listed}
		list := app.BuildListMicrosoftSignIns(lister, func() time.Time { return signInNow })

		for _, tier := range []domain.AuthSessionIdentityType{domain.AuthSessionIdentityAnonymous, "", "unknown"} {
			_, err := list(t.Context(), tier, identity)
			require.ErrorIs(t, err, domain.ErrAuthSessionTierRefused)
		}
		require.Empty(t, lister.calls)
	})

	t.Run("returns a store error", func(t *testing.T) {
		t.Parallel()
		boom := errors.New("boom")
		list := app.BuildListMicrosoftSignIns(&fakeSignInLister{err: boom}, func() time.Time { return signInNow })

		_, err := list(t.Context(), domain.AuthSessionIdentityMicrosoft, identity)
		require.ErrorIs(t, err, boom)
	})
}
