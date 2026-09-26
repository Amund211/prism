package app_test

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/authflowtoken"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/signing"
)

type fakeMicrosoftSignIn struct {
	authorizeState     string
	authorizeChallenge string

	signInCalls    int
	signInCode     string
	signInVerifier string
	account        domain.MinecraftAccount
	err            error
}

func (f *fakeMicrosoftSignIn) AuthorizeURL(state, codeChallenge string) string {
	f.authorizeState = state
	f.authorizeChallenge = codeChallenge
	return "https://login.example.com/authorize?state=" + state
}

func (f *fakeMicrosoftSignIn) SignIn(_ context.Context, code, codeVerifier string) (domain.MinecraftAccount, error) {
	f.signInCalls++
	f.signInCode = code
	f.signInVerifier = codeVerifier
	return f.account, f.err
}

func newFlowSealer(t *testing.T) authflowtoken.Signed {
	t.Helper()
	sealer, err := authflowtoken.NewSigned([][]byte{[]byte(strings.Repeat("k", signing.MinKeyLength))})
	require.NoError(t, err)
	return sealer
}

var signInNow = time.Date(2026, 9, 26, 12, 0, 0, 0, time.UTC)

func TestStartMicrosoftSignIn(t *testing.T) {
	t.Parallel()

	microsoft := &fakeMicrosoftSignIn{}
	sealer := newFlowSealer(t)
	start := app.BuildStartMicrosoftSignIn(microsoft, sealer, func() time.Time { return signInNow })

	started, err := start(t.Context())
	require.NoError(t, err)
	require.Equal(t, "https://login.example.com/authorize?state="+microsoft.authorizeState, started.AuthorizeURL)
	require.Equal(t, 10*time.Minute, started.ExpiresIn)

	flow, err := sealer.Unseal(started.FlowCookie)
	require.NoError(t, err)
	require.Equal(t, microsoft.authorizeState, flow.State)
	require.Equal(t, signInNow.Add(10*time.Minute), flow.ExpiresAt)

	// RFC 7636: 43+ chars, and S256 of it is the challenge sent to Microsoft.
	require.GreaterOrEqual(t, len(flow.Verifier), 43)
	digest := sha256.Sum256([]byte(flow.Verifier))
	require.Equal(t, base64.RawURLEncoding.EncodeToString(digest[:]), microsoft.authorizeChallenge)

	require.GreaterOrEqual(t, len(flow.State), 43)
	require.NotEqual(t, flow.State, flow.Verifier)

	t.Run("every flow is fresh", func(t *testing.T) {
		t.Parallel()
		other, err := start(t.Context())
		require.NoError(t, err)
		otherFlow, err := sealer.Unseal(other.FlowCookie)
		require.NoError(t, err)
		require.NotEqual(t, flow.State, otherFlow.State)
		require.NotEqual(t, flow.Verifier, otherFlow.Verifier)
	})
}

func TestFinishMicrosoftSignIn(t *testing.T) {
	t.Parallel()

	account := domain.MinecraftAccount{UUID: "a937646bf11544c38dbf9ae4a65669a0", Username: "Skydeath"}
	flow := domain.MicrosoftSignInFlow{State: "the-state", Verifier: "the-verifier", ExpiresAt: signInNow.Add(10 * time.Minute)}

	setup := func(t *testing.T, now time.Time) (*fakeMicrosoftSignIn, app.FinishMicrosoftSignIn, string) {
		t.Helper()
		microsoft := &fakeMicrosoftSignIn{account: account}
		sealer := newFlowSealer(t)
		cookie, err := sealer.Seal(flow)
		require.NoError(t, err)
		return microsoft, app.BuildFinishMicrosoftSignIn(microsoft, sealer, func() time.Time { return now }), cookie
	}

	t.Run("redeems the code with the flow's verifier", func(t *testing.T) {
		t.Parallel()
		microsoft, finish, cookie := setup(t, signInNow.Add(5*time.Minute))

		got, err := finish(t.Context(), cookie, "the-state", "the-code")
		require.NoError(t, err)
		require.Equal(t, account, got)
		require.Equal(t, "the-code", microsoft.signInCode)
		require.Equal(t, "the-verifier", microsoft.signInVerifier)
	})

	t.Run("passes the chain's error through", func(t *testing.T) {
		t.Parallel()
		microsoft, finish, cookie := setup(t, signInNow)
		microsoft.err = domain.ErrClientNotApproved

		_, err := finish(t.Context(), cookie, "the-state", "the-code")
		require.ErrorIs(t, err, domain.ErrClientNotApproved)
	})

	// Each of these must refuse before the code is redeemed: redeeming
	// first is the login-CSRF the flow cookie exists to stop.
	for _, tc := range []struct {
		name   string
		now    time.Time
		cookie func(valid string) string
		state  string
		want   error
	}{
		{"no cookie", signInNow, func(string) string { return "" }, "the-state", domain.ErrMicrosoftSignInFlowMissing},
		{"bad cookie", signInNow, func(v string) string { return v + "x" }, "the-state", domain.ErrMicrosoftSignInFlowInvalid},
		{"expired", flow.ExpiresAt, func(v string) string { return v }, "the-state", domain.ErrMicrosoftSignInFlowExpired},
		{"state mismatch", signInNow, func(v string) string { return v }, "other-state", domain.ErrMicrosoftSignInStateMismatch},
		{"empty state", signInNow, func(v string) string { return v }, "", domain.ErrMicrosoftSignInStateMismatch},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			microsoft, finish, cookie := setup(t, tc.now)

			_, err := finish(t.Context(), tc.cookie(cookie), tc.state, "the-code")
			require.ErrorIs(t, err, tc.want)
			require.Zero(t, microsoft.signInCalls)
		})
	}

	t.Run("errors never quote the state or the code", func(t *testing.T) {
		t.Parallel()
		microsoft, finish, cookie := setup(t, signInNow)
		microsoft.err = errors.New("unexpected")

		for _, state := range []string{"the-state", "other-state"} {
			_, err := finish(t.Context(), cookie, state, "the-code")
			require.Error(t, err)
			require.NotContains(t, err.Error(), "the-state")
			require.NotContains(t, err.Error(), "other-state")
			require.NotContains(t, err.Error(), "the-code")
			require.NotContains(t, err.Error(), "the-verifier")
		}
	})
}
