package app_test

import (
	"bytes"
	"context"
	"crypto/sha256"
	"errors"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
)

type rotateCall struct {
	presentedHash []byte
	newHash       []byte
	now           time.Time
	grace         time.Duration
	idleWindow    time.Duration
}

type fakeCredentialStore struct {
	stored    domain.UserCredential
	findErr   error
	rotateErr error
	deleteErr error

	finds   int
	rotates []rotateCall
	deletes int
}

func (f *fakeCredentialStore) Find(_ context.Context, hash []byte, _ time.Time) (domain.UserCredential, error) {
	f.finds++
	if f.findErr != nil {
		return domain.UserCredential{}, f.findErr
	}
	if !bytes.Equal(hash, f.stored.Hash) {
		return domain.UserCredential{}, domain.ErrUserCredentialNotFound
	}
	return f.stored, nil
}

func (f *fakeCredentialStore) Rotate(_ context.Context, presentedHash, newHash []byte, now time.Time, grace, idleWindow time.Duration) (domain.UserCredential, error) {
	f.rotates = append(f.rotates, rotateCall{presentedHash, newHash, now, grace, idleWindow})
	if f.rotateErr != nil {
		return domain.UserCredential{}, f.rotateErr
	}
	next := f.stored
	next.Hash = newHash
	next.ExpiresAt = now.Add(idleWindow)
	return next, nil
}

func (f *fakeCredentialStore) DeleteByIdentityOf(_ context.Context, hash []byte, _ time.Time) (string, int, error) {
	f.deletes++
	if f.deleteErr != nil {
		return "", 0, f.deleteErr
	}
	if !bytes.Equal(hash, f.stored.Hash) {
		return "", 0, domain.ErrUserCredentialNotFound
	}
	return f.stored.IdentityKey, 3, nil
}

const presentedCredential = "the-presented-credential-0123456789abcdefgh"

func storeHolding(clientType domain.MicrosoftClientType) *fakeCredentialStore {
	hash := sha256.Sum256([]byte(presentedCredential))
	return &fakeCredentialStore{stored: domain.UserCredential{
		Hash:        hash[:],
		IdentityKey: "a937646bf11544c38dbf9ae4a65669a0",
		ClientType:  clientType,
		CreatedAt:   signInNow.Add(-10 * 24 * time.Hour),
		ExpiresAt:   signInNow.Add(80 * 24 * time.Hour),
	}}
}

func TestRecoverMicrosoftSession(t *testing.T) {
	t.Parallel()

	now := signInNow

	setup := func(t *testing.T, store *fakeCredentialStore, guard allowFunc) app.RecoverMicrosoftSession {
		t.Helper()
		return app.BuildRecoverMicrosoftSession(store, newTestSealer(t), guard, fixedNow(now), fixedLineage())
	}

	for _, clientType := range []domain.MicrosoftClientType{domain.MicrosoftClientRainbow, domain.MicrosoftClientPrism} {
		t.Run("rotates the credential and starts a new chain for "+string(clientType), func(t *testing.T) {
			t.Parallel()
			store := storeHolding(clientType)
			recoverSession := setup(t, store, allowAll())

			got, err := recoverSession(t.Context(), presentedCredential, clientType, "ip-hash")
			require.NoError(t, err)
			require.Equal(t, clientType, got.ClientType)

			require.GreaterOrEqual(t, len(got.Credential), 43, "32 random bytes")
			require.NotEqual(t, presentedCredential, got.Credential)
			newHash := sha256.Sum256([]byte(got.Credential))
			require.Equal(t, []rotateCall{{
				presentedHash: store.stored.Hash,
				newHash:       newHash[:],
				now:           now,
				grace:         time.Minute,
				idleWindow:    90 * 24 * time.Hour,
			}}, store.rotates)

			sess, err := newTestSealer(t).Unseal(t.Context(), got.Session.ID)
			require.NoError(t, err)
			require.Equal(t, domain.AuthSessionIdentityMicrosoft, sess.IdentityType)
			require.Equal(t, "a937646bf11544c38dbf9ae4a65669a0", sess.IdentityKey)
			require.Equal(t, now, sess.LineageIssuedAt, "a recover starts a new chain")
			require.Equal(t, testLineage, sess.Lineage)
			require.Equal(t, now.Add(authSessionTTL), got.Session.ExpiresAt)
			require.Equal(t, now.Add(authMaxSessionAge), got.Session.LifetimeEndsAt)
		})
	}

	t.Run("consults the guard with the stored identity", func(t *testing.T) {
		t.Parallel()
		called := false
		recoverSession := setup(t, storeHolding(domain.MicrosoftClientPrism), func(_ context.Context, identityType domain.AuthSessionIdentityType, identityKey string, ipHash string, guardNow time.Time) error {
			called = true
			require.Equal(t, domain.AuthSessionIdentityMicrosoft, identityType)
			require.Equal(t, "a937646bf11544c38dbf9ae4a65669a0", identityKey)
			require.Equal(t, "ip-hash", ipHash)
			require.Equal(t, now, guardNow)
			return nil
		})

		_, err := recoverSession(t.Context(), presentedCredential, domain.MicrosoftClientPrism, "ip-hash")
		require.NoError(t, err)
		require.True(t, called)
	})

	t.Run("a guard refusal does not spend the credential", func(t *testing.T) {
		t.Parallel()
		store := storeHolding(domain.MicrosoftClientPrism)
		recoverSession := setup(t, store, func(context.Context, domain.AuthSessionIdentityType, string, string, time.Time) error {
			return domain.ErrAuthSessionIssuanceRefused
		})

		_, err := recoverSession(t.Context(), presentedCredential, domain.MicrosoftClientPrism, "ip-hash")
		require.ErrorIs(t, err, domain.ErrAuthSessionIssuanceRefused)
		require.Empty(t, store.rotates)
	})

	t.Run("a credential presented by the other client is refused and not spent", func(t *testing.T) {
		t.Parallel()
		store := storeHolding(domain.MicrosoftClientRainbow)
		recoverSession := setup(t, store, allowAll())

		_, err := recoverSession(t.Context(), presentedCredential, domain.MicrosoftClientPrism, "ip-hash")
		require.ErrorIs(t, err, domain.ErrUserCredentialClientMismatch)
		require.Empty(t, store.rotates)
	})

	for _, want := range []error{domain.ErrUserCredentialNotFound, domain.ErrUserCredentialStale} {
		t.Run("passes "+want.Error()+" through from find", func(t *testing.T) {
			t.Parallel()
			store := storeHolding(domain.MicrosoftClientPrism)
			store.findErr = want
			recoverSession := setup(t, store, allowAll())

			_, err := recoverSession(t.Context(), presentedCredential, domain.MicrosoftClientPrism, "ip-hash")
			require.ErrorIs(t, err, want)
			require.Empty(t, store.rotates)
		})

		t.Run("passes "+want.Error()+" through from rotate", func(t *testing.T) {
			t.Parallel()
			store := storeHolding(domain.MicrosoftClientPrism)
			store.rotateErr = want
			recoverSession := setup(t, store, allowAll())

			_, err := recoverSession(t.Context(), presentedCredential, domain.MicrosoftClientPrism, "ip-hash")
			require.ErrorIs(t, err, want)
		})
	}

	t.Run("errors never quote the credential", func(t *testing.T) {
		t.Parallel()
		for _, store := range []*fakeCredentialStore{
			{findErr: domain.ErrUserCredentialStale},
			{rotateErr: errors.New("db down")},
		} {
			store.stored = storeHolding(domain.MicrosoftClientPrism).stored
			_, err := setup(t, store, allowAll())(t.Context(), presentedCredential, domain.MicrosoftClientPrism, "ip-hash")
			require.Error(t, err)
			require.NotContains(t, err.Error(), presentedCredential)
		}
	})
}

func TestLogoutMicrosoft(t *testing.T) {
	t.Parallel()

	t.Run("deletes by the identity of the presented credential", func(t *testing.T) {
		t.Parallel()
		store := storeHolding(domain.MicrosoftClientPrism)
		logout := app.BuildLogoutMicrosoft(store, fixedNow(signInNow))

		identityKey, deleted, err := logout(t.Context(), presentedCredential)
		require.NoError(t, err)
		require.Equal(t, "a937646bf11544c38dbf9ae4a65669a0", identityKey)
		require.Equal(t, 3, deleted)
		require.Equal(t, 1, store.deletes)
	})

	t.Run("passes a refusal through", func(t *testing.T) {
		t.Parallel()
		store := storeHolding(domain.MicrosoftClientPrism)
		logout := app.BuildLogoutMicrosoft(store, fixedNow(signInNow))

		_, _, err := logout(t.Context(), "some-other-credential")
		require.ErrorIs(t, err, domain.ErrUserCredentialNotFound)
	})
}
