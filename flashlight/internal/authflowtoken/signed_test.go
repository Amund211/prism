package authflowtoken_test

import (
	"encoding/base64"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/authflowtoken"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/signing"
)

func testKey(b byte) []byte {
	return []byte(strings.Repeat(string(rune('a'+b)), signing.MinKeyLength))
}

func newSigned(t *testing.T, keys ...[]byte) authflowtoken.Signed {
	t.Helper()
	s, err := authflowtoken.NewSigned(keys)
	require.NoError(t, err)
	return s
}

var testFlow = domain.MicrosoftSignInFlow{
	State:     "the-state",
	Verifier:  "the-verifier",
	ExpiresAt: time.Date(2026, 9, 26, 12, 10, 0, 0, time.UTC),
}

func TestNewSigned(t *testing.T) {
	t.Parallel()

	_, err := authflowtoken.NewSigned(nil)
	require.ErrorIs(t, err, signing.ErrInvalidConfig)

	_, err = authflowtoken.NewSigned([][]byte{[]byte("short")})
	require.ErrorIs(t, err, signing.ErrInvalidConfig)
}

func TestSealUnseal(t *testing.T) {
	t.Parallel()

	t.Run("round trips", func(t *testing.T) {
		t.Parallel()
		s := newSigned(t, testKey(0))

		value, err := s.Seal(testFlow)
		require.NoError(t, err)
		require.True(t, strings.HasPrefix(value, "flflow_"))

		flow, err := s.Unseal(value)
		require.NoError(t, err)
		require.Equal(t, testFlow, flow)
	})

	t.Run("is a valid cookie value", func(t *testing.T) {
		t.Parallel()
		value, err := newSigned(t, testKey(0)).Seal(testFlow)
		require.NoError(t, err)
		require.False(t, strings.ContainsAny(value, " \",;\\"))
	})

	t.Run("any key verifies, the first signs", func(t *testing.T) {
		t.Parallel()
		old := newSigned(t, testKey(1))
		rotated := newSigned(t, testKey(0), testKey(1))

		value, err := old.Seal(testFlow)
		require.NoError(t, err)
		_, err = rotated.Unseal(value)
		require.NoError(t, err)

		value, err = rotated.Seal(testFlow)
		require.NoError(t, err)
		_, err = old.Unseal(value)
		require.ErrorIs(t, err, domain.ErrMicrosoftSignInFlowInvalid)
	})

	t.Run("refuses to seal an incomplete flow", func(t *testing.T) {
		t.Parallel()
		s := newSigned(t, testKey(0))
		for _, flow := range []domain.MicrosoftSignInFlow{
			{Verifier: "v", ExpiresAt: testFlow.ExpiresAt},
			{State: "s", ExpiresAt: testFlow.ExpiresAt},
			{State: "s", Verifier: "v"},
		} {
			_, err := s.Seal(flow)
			require.Error(t, err)
		}
	})

	t.Run("rejects anything it did not sign", func(t *testing.T) {
		t.Parallel()
		s := newSigned(t, testKey(0))
		value, err := s.Seal(testFlow)
		require.NoError(t, err)
		signed, signature, ok := strings.Cut(value, ".")
		require.True(t, ok)

		// A session handle signed with the same key must not verify.
		sessionLike := "flsess_" + strings.TrimPrefix(signed, "flflow_")
		sessionLike += "." + base64.RawURLEncoding.EncodeToString(signing.Sign(testKey(0), sessionLike))

		for name, bad := range map[string]string{
			"empty":               "",
			"no separator":        signed,
			"tampered payload":    signed + "x." + signature,
			"bad signature":       signed + ".AAAA",
			"non-base64 sig":      signed + ".***",
			"other prefix":        sessionLike,
			"other key":           mustSeal(t, newSigned(t, testKey(2))),
			"over the length cap": strings.Repeat("a", 2000) + "." + signature,
		} {
			t.Run(name, func(t *testing.T) {
				t.Parallel()
				_, err := s.Unseal(bad)
				require.ErrorIs(t, err, domain.ErrMicrosoftSignInFlowInvalid)
			})
		}
	})

	t.Run("rejects another typ", func(t *testing.T) {
		t.Parallel()
		key := testKey(0)
		signed := "flflow_" + base64.RawURLEncoding.EncodeToString([]byte(`{"typ":"flflow/2","msState":"s","msVerifier":"v","expiresAtUnixMillis":1}`))
		value := signed + "." + base64.RawURLEncoding.EncodeToString(signing.Sign(key, signed))

		_, err := newSigned(t, key).Unseal(value)
		require.ErrorIs(t, err, domain.ErrMicrosoftSignInFlowInvalid)
	})

	t.Run("errors never quote the value", func(t *testing.T) {
		t.Parallel()
		s := newSigned(t, testKey(0))
		value := mustSeal(t, newSigned(t, testKey(2)))
		_, err := s.Unseal(value)
		require.Error(t, err)
		require.NotContains(t, err.Error(), value)
		require.NotContains(t, err.Error(), testFlow.State)
	})
}

func mustSeal(t *testing.T, s authflowtoken.Signed) string {
	t.Helper()
	value, err := s.Seal(testFlow)
	require.NoError(t, err)
	return value
}
