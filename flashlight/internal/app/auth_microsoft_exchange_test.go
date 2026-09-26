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
	"github.com/Amund211/flashlight/internal/domain"
)

type fakeCredentialRepository struct {
	inserted []domain.UserCredential
	err      error
}

func (f *fakeCredentialRepository) Insert(_ context.Context, cred domain.UserCredential) error {
	if f.err != nil {
		return f.err
	}
	f.inserted = append(f.inserted, cred)
	return nil
}

func TestExchangeMicrosoftSignIn(t *testing.T) {
	t.Parallel()

	verifier := strings.Repeat("v", 43)
	digest := sha256.Sum256([]byte(verifier))
	challenge := base64.RawURLEncoding.EncodeToString(digest[:])
	now := signInNow.Add(30 * time.Second)

	sealResult := func(t *testing.T, clientType domain.MicrosoftClientType) string {
		t.Helper()
		result, err := newResultSealer(t).Seal(domain.MicrosoftSignInResult{
			Account:    domain.MinecraftAccount{UUID: "a937646b-f115-44c3-8dbf-9ae4a65669a0", Username: "Skydeath"},
			ClientType: clientType,
			Challenge:  challenge,
			ExpiresAt:  signInNow.Add(60 * time.Second),
		})
		require.NoError(t, err)
		return result
	}

	setup := func(t *testing.T, now time.Time, guard allowFunc) (*fakeCredentialRepository, app.ExchangeMicrosoftSignIn) {
		t.Helper()
		repo := &fakeCredentialRepository{}
		return repo, app.BuildExchangeMicrosoftSignIn(newResultSealer(t), repo, newTestSealer(t), guard, fixedNow(now), fixedLineage())
	}

	for _, clientType := range []domain.MicrosoftClientType{domain.MicrosoftClientRainbow, domain.MicrosoftClientPrism} {
		t.Run("mints a credential and a microsoft session for "+string(clientType), func(t *testing.T) {
			t.Parallel()
			repo, exchange := setup(t, now, allowAll())

			got, err := exchange(t.Context(), sealResult(t, clientType), verifier, "ip-hash")
			require.NoError(t, err)
			require.Equal(t, clientType, got.ClientType)

			require.GreaterOrEqual(t, len(got.Credential), 43, "32 random bytes")
			credentialHash := sha256.Sum256([]byte(got.Credential))
			require.Equal(t, []domain.UserCredential{{
				Hash:        credentialHash[:],
				IdentityKey: "a937646bf11544c38dbf9ae4a65669a0",
				ClientType:  clientType,
				CreatedAt:   now,
				ExpiresAt:   now.Add(90 * 24 * time.Hour),
			}}, repo.inserted)

			sess, err := newTestSealer(t).Unseal(t.Context(), got.Session.ID)
			require.NoError(t, err)
			require.Equal(t, domain.AuthSessionIdentityMicrosoft, sess.IdentityType)
			require.Equal(t, "a937646bf11544c38dbf9ae4a65669a0", sess.IdentityKey)
			require.Equal(t, now, sess.CreatedAt)
			require.Equal(t, now, sess.LineageIssuedAt)
			require.Equal(t, testLineage, sess.Lineage)
			require.Equal(t, now.Add(authSessionTTL), got.Session.ExpiresAt)
			require.Equal(t, now.Add(authRefreshWindow), got.Session.RefreshUntil)
			require.Equal(t, now.Add(authMaxSessionAge), got.Session.LifetimeEndsAt)
		})
	}

	t.Run("replaying a result mints a fresh credential each time", func(t *testing.T) {
		t.Parallel()
		repo, exchange := setup(t, now, allowAll())
		result := sealResult(t, domain.MicrosoftClientPrism)

		first, err := exchange(t.Context(), result, verifier, "ip-hash")
		require.NoError(t, err)
		second, err := exchange(t.Context(), result, verifier, "ip-hash")
		require.NoError(t, err)
		require.NotEqual(t, first.Credential, second.Credential)
		require.Len(t, repo.inserted, 2)
	})

	t.Run("consults the guard with the verified identity", func(t *testing.T) {
		t.Parallel()
		called := false
		_, exchange := setup(t, now, func(_ context.Context, identityType domain.AuthSessionIdentityType, identityKey string, ipHash string, guardNow time.Time) error {
			called = true
			require.Equal(t, domain.AuthSessionIdentityMicrosoft, identityType)
			require.Equal(t, "a937646bf11544c38dbf9ae4a65669a0", identityKey)
			require.Equal(t, "ip-hash", ipHash)
			require.Equal(t, now, guardNow)
			return nil
		})

		_, err := exchange(t.Context(), sealResult(t, domain.MicrosoftClientPrism), verifier, "ip-hash")
		require.NoError(t, err)
		require.True(t, called)
	})

	t.Run("a guard refusal writes nothing", func(t *testing.T) {
		t.Parallel()
		repo, exchange := setup(t, now, func(context.Context, domain.AuthSessionIdentityType, string, string, time.Time) error {
			return domain.ErrAuthSessionIssuanceRefused
		})

		_, err := exchange(t.Context(), sealResult(t, domain.MicrosoftClientPrism), verifier, "ip-hash")
		require.ErrorIs(t, err, domain.ErrAuthSessionIssuanceRefused)
		require.Empty(t, repo.inserted)
	})

	t.Run("passes a repository failure through", func(t *testing.T) {
		t.Parallel()
		repo, exchange := setup(t, now, allowAll())
		repo.err = errors.New("db down")

		_, err := exchange(t.Context(), sealResult(t, domain.MicrosoftClientPrism), verifier, "ip-hash")
		require.Error(t, err)
	})

	for _, tc := range []struct {
		name     string
		now      time.Time
		result   func(valid string) string
		verifier string
		want     error
	}{
		{"a tampered result", now, func(v string) string { return v + "x" }, verifier, domain.ErrMicrosoftSignInResultInvalid},
		{"an expired result", signInNow.Add(60 * time.Second), func(v string) string { return v }, verifier, domain.ErrMicrosoftSignInResultExpired},
		{"the wrong verifier", now, func(v string) string { return v }, strings.Repeat("w", 43), domain.ErrMicrosoftSignInVerifierMismatch},
		{"the challenge as verifier", now, func(v string) string { return v }, challenge, domain.ErrMicrosoftSignInVerifierMismatch},
	} {
		t.Run("refuses "+tc.name, func(t *testing.T) {
			t.Parallel()
			repo, exchange := setup(t, tc.now, allowAll())

			_, err := exchange(t.Context(), tc.result(sealResult(t, domain.MicrosoftClientPrism)), tc.verifier, "ip-hash")
			require.ErrorIs(t, err, tc.want)
			require.Empty(t, repo.inserted)
		})
	}

	t.Run("errors never quote the result or the verifier", func(t *testing.T) {
		t.Parallel()
		_, exchange := setup(t, now, allowAll())
		result := sealResult(t, domain.MicrosoftClientPrism)

		for _, v := range []string{verifier, strings.Repeat("w", 43)} {
			_, err := exchange(t.Context(), result+"x", v, "ip-hash")
			require.Error(t, err)
			require.NotContains(t, err.Error(), result)
			require.NotContains(t, err.Error(), v)
		}
	})
}
