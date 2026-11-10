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

var (
	testRainbowTarget = domain.MicrosoftSignInTarget{
		ClientType: domain.MicrosoftClientRainbow,
		URL:        "https://prismoverlay.com",
		Challenge:  "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
	}
	testPrismTarget = domain.MicrosoftSignInTarget{
		ClientType:  domain.MicrosoftClientPrism,
		URL:         "http://127.0.0.1:52345/callback",
		Challenge:   "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
		ClientState: "prism-nonce",
	}
)

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

	t.Run("round trips a client flow", func(t *testing.T) {
		t.Parallel()
		s := newSigned(t, testKey(0))

		for _, target := range []domain.MicrosoftSignInTarget{
			testRainbowTarget,
			testPrismTarget,
			{ClientType: domain.MicrosoftClientPrism, URL: "http://127.0.0.1:1/callback", Challenge: testPrismTarget.Challenge},
		} {
			flow := testFlow
			flow.Target = &target
			value, err := s.Seal(flow)
			require.NoError(t, err)

			got, err := s.Unseal(value)
			require.NoError(t, err)
			require.Equal(t, flow, got)
		}
	})

	t.Run("the largest client flow fits the cap", func(t *testing.T) {
		t.Parallel()
		flow := testFlow
		flow.State = strings.Repeat("s", 43)
		flow.Verifier = strings.Repeat("v", 43)
		flow.Target = &domain.MicrosoftSignInTarget{
			ClientType:  domain.MicrosoftClientRainbow,
			URL:         strings.Repeat("u", domain.MicrosoftSignInReturnMaxLength),
			Challenge:   strings.Repeat("c", 43),
			ClientState: strings.Repeat("n", domain.MicrosoftSignInClientStateMaxLength),
		}
		_, err := newSigned(t, testKey(0)).Seal(flow)
		require.NoError(t, err)
	})

	t.Run("refuses to seal an incomplete target", func(t *testing.T) {
		t.Parallel()
		s := newSigned(t, testKey(0))
		for _, target := range []domain.MicrosoftSignInTarget{
			{URL: "https://prismoverlay.com", Challenge: "c"},
			{ClientType: "other", URL: "https://prismoverlay.com", Challenge: "c"},
			{ClientType: domain.MicrosoftClientRainbow, Challenge: "c"},
			{ClientType: domain.MicrosoftClientRainbow, URL: "https://prismoverlay.com"},
		} {
			flow := testFlow
			flow.Target = &target
			_, err := s.Seal(flow)
			require.Error(t, err)
		}
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
			"over the length cap": strings.Repeat("a", 3000) + "." + signature,
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

	t.Run("rejects an incomplete target", func(t *testing.T) {
		t.Parallel()
		key := testKey(0)
		for _, extra := range []string{
			`"clientType":"other","return":"r","challenge":"c"`,
			`"clientType":"rainbow","challenge":"c"`,
			`"clientType":"rainbow","return":"r"`,
			`"return":"r","challenge":"c"`,
		} {
			signed := "flflow_" + base64.RawURLEncoding.EncodeToString([]byte(`{"typ":"flflow/1","msState":"s","msVerifier":"v","expiresAtUnixMillis":1,`+extra+`}`))
			value := signed + "." + base64.RawURLEncoding.EncodeToString(signing.Sign(key, signed))

			_, err := newSigned(t, key).Unseal(value)
			require.ErrorIs(t, err, domain.ErrMicrosoftSignInFlowInvalid, extra)
		}
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
