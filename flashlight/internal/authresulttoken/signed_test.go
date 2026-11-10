package authresulttoken_test

import (
	"context"
	"encoding/base64"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/authflowtoken"
	"github.com/Amund211/flashlight/internal/authresulttoken"
	"github.com/Amund211/flashlight/internal/authsessiontoken"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/signing"
)

func testKey(b byte) []byte {
	return []byte(strings.Repeat(string(rune('a'+b)), signing.MinKeyLength))
}

func newSigned(t *testing.T, keys ...[]byte) authresulttoken.Signed {
	t.Helper()
	s, err := authresulttoken.NewSigned(keys)
	require.NoError(t, err)
	return s
}

var testResult = domain.MicrosoftSignInResult{
	Account:    domain.MinecraftAccount{UUID: "a937646bf11544c38dbf9ae4a65669a0", Username: "Skydeath"},
	ClientType: domain.MicrosoftClientPrism,
	Challenge:  "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
	ExpiresAt:  time.Date(2026, 9, 26, 12, 1, 0, 0, time.UTC),
}

func mustSeal(t *testing.T, s authresulttoken.Signed) string {
	t.Helper()
	value, err := s.Seal(testResult)
	require.NoError(t, err)
	return value
}

func TestNewSigned(t *testing.T) {
	t.Parallel()

	_, err := authresulttoken.NewSigned(nil)
	require.ErrorIs(t, err, signing.ErrInvalidConfig)

	_, err = authresulttoken.NewSigned([][]byte{[]byte("short")})
	require.ErrorIs(t, err, signing.ErrInvalidConfig)
}

func TestSealUnseal(t *testing.T) {
	t.Parallel()

	t.Run("round trips", func(t *testing.T) {
		t.Parallel()
		s := newSigned(t, testKey(0))

		value := mustSeal(t, s)
		require.True(t, strings.HasPrefix(value, "flresult_"))

		got, err := s.Unseal(value)
		require.NoError(t, err)
		require.Equal(t, testResult, got)
	})

	t.Run("is safe in a query and a fragment", func(t *testing.T) {
		t.Parallel()
		value := mustSeal(t, newSigned(t, testKey(0)))
		require.Regexp(t, `^[A-Za-z0-9_.-]+$`, value)
	})

	t.Run("any key verifies, the first signs", func(t *testing.T) {
		t.Parallel()
		old := newSigned(t, testKey(1))
		rotated := newSigned(t, testKey(0), testKey(1))

		_, err := rotated.Unseal(mustSeal(t, old))
		require.NoError(t, err)

		_, err = old.Unseal(mustSeal(t, rotated))
		require.ErrorIs(t, err, domain.ErrMicrosoftSignInResultInvalid)
	})

	t.Run("refuses to seal an incomplete result", func(t *testing.T) {
		t.Parallel()
		s := newSigned(t, testKey(0))
		for _, mutate := range []func(*domain.MicrosoftSignInResult){
			func(r *domain.MicrosoftSignInResult) { r.Account.UUID = "" },
			func(r *domain.MicrosoftSignInResult) { r.ClientType = "" },
			func(r *domain.MicrosoftSignInResult) { r.ClientType = "other" },
			func(r *domain.MicrosoftSignInResult) { r.Challenge = "" },
			func(r *domain.MicrosoftSignInResult) { r.ExpiresAt = time.Time{} },
		} {
			result := testResult
			mutate(&result)
			_, err := s.Seal(result)
			require.Error(t, err)
		}
	})

	t.Run("rejects anything it did not sign", func(t *testing.T) {
		t.Parallel()
		s := newSigned(t, testKey(0))
		value := mustSeal(t, s)
		signed, signature, ok := strings.Cut(value, ".")
		require.True(t, ok)

		for name, bad := range map[string]string{
			"empty":               "",
			"no separator":        signed,
			"tampered payload":    signed + "x." + signature,
			"bad signature":       signed + ".AAAA",
			"non-base64 sig":      signed + ".***",
			"other key":           mustSeal(t, newSigned(t, testKey(2))),
			"over the length cap": strings.Repeat("a", 2000) + "." + signature,
		} {
			t.Run(name, func(t *testing.T) {
				t.Parallel()
				_, err := s.Unseal(bad)
				require.ErrorIs(t, err, domain.ErrMicrosoftSignInResultInvalid)
			})
		}
	})

	// The flow cookie shares AUTH_FLOW_SIGNING_KEYS, so the prefix is all
	// that keeps one from verifying as the other.
	t.Run("a flow cookie and a result never verify as each other", func(t *testing.T) {
		t.Parallel()
		key := testKey(0)
		flows, err := authflowtoken.NewSigned([][]byte{key})
		require.NoError(t, err)
		results := newSigned(t, key)

		flow, err := flows.Seal(domain.MicrosoftSignInFlow{State: "s", Verifier: "v", ExpiresAt: testResult.ExpiresAt})
		require.NoError(t, err)
		_, err = results.Unseal(flow)
		require.ErrorIs(t, err, domain.ErrMicrosoftSignInResultInvalid)

		_, err = flows.Unseal(mustSeal(t, results))
		require.ErrorIs(t, err, domain.ErrMicrosoftSignInFlowInvalid)
	})

	t.Run("a session handle never verifies as a result", func(t *testing.T) {
		t.Parallel()
		key := testKey(0)
		sessions, err := authsessiontoken.NewSigned([][]byte{key})
		require.NoError(t, err)
		now := testResult.ExpiresAt
		sess, err := sessions.Seal(context.Background(), domain.AuthSession{
			IdentityType:    domain.AuthSessionIdentityAnonymous,
			IdentityKey:     "user",
			CreatedAt:       now,
			LineageIssuedAt: now,
			Lineage:         "fllineage_x",
		})
		require.NoError(t, err)

		_, err = newSigned(t, key).Unseal(sess.ID)
		require.ErrorIs(t, err, domain.ErrMicrosoftSignInResultInvalid)

		_, err = sessions.Unseal(context.Background(), mustSeal(t, newSigned(t, key)))
		require.ErrorIs(t, err, domain.ErrAuthSessionNotFound)
	})

	t.Run("rejects another typ", func(t *testing.T) {
		t.Parallel()
		key := testKey(0)
		for _, typ := range []string{"flflow/1", "flresult/2", ""} {
			signed := "flresult_" + base64.RawURLEncoding.EncodeToString([]byte(`{"typ":"`+typ+`","uuid":"u","name":"n","clientType":"prism","challenge":"c","expiresAtUnixMillis":1}`))
			value := signed + "." + base64.RawURLEncoding.EncodeToString(signing.Sign(key, signed))

			_, err := newSigned(t, key).Unseal(value)
			require.ErrorIs(t, err, domain.ErrMicrosoftSignInResultInvalid, typ)
		}
	})

	t.Run("errors never quote the value", func(t *testing.T) {
		t.Parallel()
		value := mustSeal(t, newSigned(t, testKey(2)))
		_, err := newSigned(t, testKey(0)).Unseal(value)
		require.Error(t, err)
		require.NotContains(t, err.Error(), value)
		require.NotContains(t, err.Error(), testResult.Challenge)
	})
}
