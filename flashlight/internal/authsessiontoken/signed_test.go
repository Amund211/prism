package authsessiontoken_test

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/authsessiontoken"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/signing"
)

var testTime = time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC)

func testKey(t *testing.T, fill byte) []byte {
	t.Helper()
	key := make([]byte, signing.MinKeyLength)
	for i := range key {
		key[i] = fill
	}
	return key
}

func newSigned(t *testing.T, keys ...[]byte) authsessiontoken.Signed {
	t.Helper()
	sealer, err := authsessiontoken.NewSigned(keys)
	require.NoError(t, err)
	return sealer
}

func testSession() domain.AuthSession {
	return domain.AuthSession{
		IdentityType:    domain.AuthSessionIdentityAnonymous,
		IdentityKey:     "user-abc",
		CreatedAt:       testTime.Add(90 * time.Minute),
		LineageIssuedAt: testTime,
		Lineage:         "fllineage_0190d3c1-8f2a-7d3e-9c11-4a6b8e2f0d55",
		Generation:      3,
	}
}

// splitHandle returns the signed half and the signature of a handle.
func splitHandle(t *testing.T, handle string) (string, string) {
	t.Helper()
	signed, sig, ok := strings.Cut(handle, ".")
	require.True(t, ok, "handle should have a dot-separated signature")
	return signed, sig
}

func reseal(t *testing.T, sealer authsessiontoken.Signed, sess domain.AuthSession) string {
	t.Helper()
	sealed, err := sealer.Seal(context.Background(), sess)
	require.NoError(t, err)
	return sealed.ID
}

func TestSealUnsealRoundTrip(t *testing.T) {
	t.Parallel()

	ctx := context.Background()
	sealer := newSigned(t, testKey(t, 1))
	sess := testSession()

	sealed, err := sealer.Seal(ctx, sess)
	require.NoError(t, err)

	got, err := sealer.Unseal(ctx, sealed.ID)
	require.NoError(t, err)

	require.Equal(t, sealed.ID, got.ID, "the handle is the id")
	require.Equal(t, sess.IdentityType, got.IdentityType)
	require.Equal(t, sess.IdentityKey, got.IdentityKey)
	require.Equal(t, sess.CreatedAt, got.CreatedAt)
	require.Equal(t, sess.LineageIssuedAt, got.LineageIssuedAt)
	require.Equal(t, sess.Lineage, got.Lineage)
	require.Equal(t, sess.Generation, got.Generation)

	// Deadlines are derived, so they are not in the payload and must not
	// come back from Unseal pretending to be.
	require.Zero(t, got.ExpiresAt)
	require.Zero(t, got.RefreshUntil)
	require.Zero(t, got.LifetimeEndsAt)
}

func TestSealShape(t *testing.T) {
	t.Parallel()

	ctx := context.Background()
	sealer := newSigned(t, testKey(t, 1))

	sealed, err := sealer.Seal(ctx, testSession())
	require.NoError(t, err)

	// Literal, not the package constant: released rainbow throws on a
	// login response whose sessionId lacks this exact prefix, so dropping
	// it bricks every login rather than costing one re-login.
	require.True(t, strings.HasPrefix(sealed.ID, "flsess_"))
	require.Equal(t, 1, strings.Count(sealed.ID, "."))

	signedHalf, sig := splitHandle(t, sealed.ID)
	body := strings.TrimPrefix(signedHalf, "flsess_")
	rawPayload, err := base64.RawURLEncoding.DecodeString(body)
	require.NoError(t, err)
	_, err = base64.RawURLEncoding.DecodeString(sig)
	require.NoError(t, err)

	var payload map[string]any
	require.NoError(t, json.Unmarshal(rawPayload, &payload))
	require.Equal(t, "flsess/1", payload["typ"])
	require.Equal(t, "anonymous", payload["identityType"])
	require.Equal(t, "user-abc", payload["identityKey"])
	require.EqualValues(t, testTime.Add(90*time.Minute).UnixMilli(), payload["issuedAtUnixMillis"])
	require.EqualValues(t, testTime.UnixMilli(), payload["lineageIssuedAtUnixMillis"])
	require.EqualValues(t, 3, payload["generation"])

	// Neither the deadlines nor the ip hash are in there.
	for _, absent := range []string{"expiresAt", "refreshUntil", "lifetimeEndsAt", "ipHash"} {
		require.NotContains(t, payload, absent)
	}
}

func TestSealIsDeterministic(t *testing.T) {
	t.Parallel()

	// No per-handle nonce: two reseals of one parent in the same
	// millisecond mint byte-identical handles, which is the right answer
	// for rainbow's cross-tab compare ("no change").
	sealer := newSigned(t, testKey(t, 1))
	require.Equal(t, reseal(t, sealer, testSession()), reseal(t, sealer, testSession()))
}

// Seal refuses everything Unseal would, so a mint-time mistake is a 500 at
// the moment it happens rather than a 200 handing out a handle that 401s on
// every subsequent request. The login path is the one that will hit this:
// it sets neither Lineage nor LineageIssuedAt today.
func TestSealRefusesWhatUnsealWouldReject(t *testing.T) {
	t.Parallel()

	ctx := context.Background()
	sealer := newSigned(t, testKey(t, 1))

	mutations := map[string]func(*domain.AuthSession){
		"an unknown tier":         func(s *domain.AuthSession) { s.IdentityType = "microsoft" },
		"no issuedAt":             func(s *domain.AuthSession) { s.CreatedAt = time.Time{} },
		"no lineageIssuedAt":      func(s *domain.AuthSession) { s.LineageIssuedAt = time.Time{} },
		"an over-cap identityKey": func(s *domain.AuthSession) { s.IdentityKey = strings.Repeat("<", 300) },
	}

	for name, mutate := range mutations {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			sess := testSession()
			mutate(&sess)
			_, err := sealer.Seal(ctx, sess)
			require.Error(t, err)
		})
	}
}

func TestUnsealRefusals(t *testing.T) {
	t.Parallel()

	ctx := context.Background()
	sealer := newSigned(t, testKey(t, 1))
	handle := reseal(t, sealer, testSession())
	signedHalf, sig := splitHandle(t, handle)
	body := strings.TrimPrefix(signedHalf, "flsess_")

	resign := func(t *testing.T, newBody string) string {
		t.Helper()
		signedStr := "flsess_" + newBody
		return signedStr + "." + base64.RawURLEncoding.EncodeToString(signing.Sign(testKey(t, 1), signedStr))
	}
	encode := func(t *testing.T, payload map[string]any) string {
		t.Helper()
		raw, err := json.Marshal(payload)
		require.NoError(t, err)
		return base64.RawURLEncoding.EncodeToString(raw)
	}
	decoded := func(t *testing.T) map[string]any {
		t.Helper()
		raw, err := base64.RawURLEncoding.DecodeString(body)
		require.NoError(t, err)
		var payload map[string]any
		require.NoError(t, json.Unmarshal(raw, &payload))
		return payload
	}

	t.Run("structural", func(t *testing.T) {
		t.Parallel()

		for name, bad := range map[string]string{
			"empty":                    "",
			"no separator":             signedHalf,
			"signature is not base64":  signedHalf + ".not base64!",
			"empty signature":          signedHalf + ".",
			"body is not base64":       resign(t, "not base64!"),
			"body is not json":         resign(t, base64.RawURLEncoding.EncodeToString([]byte("plain text"))),
			"the prefix is missing":    body + "." + sig,
			"the prefix is misspelled": strings.Replace(handle, "flsess_", "flsess-", 1),
			"a tampered payload":       "flsess_" + encode(t, map[string]any{"typ": "flsess/1"}) + "." + sig,
			"over the length cap":      "flsess_" + strings.Repeat("A", 4096) + "." + sig,
		} {
			t.Run(name, func(t *testing.T) {
				t.Parallel()
				_, err := sealer.Unseal(ctx, bad)
				require.ErrorIs(t, err, domain.ErrAuthSessionNotFound)
			})
		}
	})

	t.Run("payload", func(t *testing.T) {
		t.Parallel()

		mutations := map[string]func(map[string]any){
			"typ is absent":             func(p map[string]any) { delete(p, "typ") },
			"typ is unknown":            func(p map[string]any) { p["typ"] = "flsess/2" },
			"typ is empty":              func(p map[string]any) { p["typ"] = "" },
			"identityType is unknown":   func(p map[string]any) { p["identityType"] = "microsoft" },
			"identityType is absent":    func(p map[string]any) { delete(p, "identityType") },
			"issuedAt is absent":        func(p map[string]any) { delete(p, "issuedAtUnixMillis") },
			"lineageIssuedAt is absent": func(p map[string]any) { delete(p, "lineageIssuedAtUnixMillis") },
			"lineageIssuedAt is zero":   func(p map[string]any) { p["lineageIssuedAtUnixMillis"] = 0 },
		}

		for name, mutate := range mutations {
			t.Run(name, func(t *testing.T) {
				t.Parallel()
				payload := decoded(t)
				mutate(payload)
				// Signed with a real key: this is about the payload, not
				// about forgery.
				_, err := sealer.Unseal(ctx, resign(t, encode(t, payload)))
				require.ErrorIs(t, err, domain.ErrAuthSessionNotFound)
			})
		}
	})

	t.Run("does not say which refusal it was", func(t *testing.T) {
		t.Parallel()
		_, err := sealer.Unseal(ctx, "flsess_garbage."+sig)
		require.ErrorIs(t, err, domain.ErrAuthSessionNotFound)
	})
}

func TestUnsealSignatureChecks(t *testing.T) {
	t.Parallel()

	ctx := context.Background()

	t.Run("refuses a handle signed with a key not in the list", func(t *testing.T) {
		t.Parallel()
		stranger := newSigned(t, testKey(t, 9))
		handle := reseal(t, stranger, testSession())

		_, err := newSigned(t, testKey(t, 1)).Unseal(ctx, handle)
		require.ErrorIs(t, err, domain.ErrAuthSessionNotFound)
	})

	t.Run("the first key signs and every key is accepted", func(t *testing.T) {
		t.Parallel()
		old := newSigned(t, testKey(t, 1))
		rotated := newSigned(t, testKey(t, 2), testKey(t, 1))

		// A handle minted before the rotation still unseals...
		_, err := rotated.Unseal(ctx, reseal(t, old, testSession()))
		require.NoError(t, err)

		// ...and new ones are signed with the new first key, so the old
		// revision no longer accepts them.
		_, err = old.Unseal(ctx, reseal(t, rotated, testSession()))
		require.ErrorIs(t, err, domain.ErrAuthSessionNotFound)
	})

	t.Run("the signature covers the prefix", func(t *testing.T) {
		t.Parallel()
		// A signature over the bare body must not verify, which is what
		// keeps TrimPrefix from ever being a security check — and what
		// stops a blob from another scheme verifying here.
		sealer := newSigned(t, testKey(t, 1))
		handle := reseal(t, sealer, testSession())
		signedHalf, _ := splitHandle(t, handle)
		body := strings.TrimPrefix(signedHalf, "flsess_")

		unprefixed := signedHalf + "." + base64.RawURLEncoding.EncodeToString(signing.Sign(testKey(t, 1), body))
		_, err := sealer.Unseal(ctx, unprefixed)
		require.ErrorIs(t, err, domain.ErrAuthSessionNotFound)
	})
}

func TestNewSignedRejectsBadKeyMaterial(t *testing.T) {
	t.Parallel()

	t.Run("an empty key list", func(t *testing.T) {
		t.Parallel()
		_, err := authsessiontoken.NewSigned(nil)
		require.ErrorIs(t, err, signing.ErrInvalidConfig)

		_, err = authsessiontoken.NewSigned([][]byte{})
		require.ErrorIs(t, err, signing.ErrInvalidConfig)
	})

	// signing.ParseKeys already enforces this, but a caller that decodes
	// the env var itself would otherwise sign every session of the entire
	// deployment with a brute-forceable key, and nothing would fail.
	t.Run("a short key, in any position", func(t *testing.T) {
		t.Parallel()
		short := make([]byte, signing.MinKeyLength-1)

		_, err := authsessiontoken.NewSigned([][]byte{short})
		require.ErrorIs(t, err, signing.ErrInvalidConfig)

		_, err = authsessiontoken.NewSigned([][]byte{testKey(t, 1), short})
		require.ErrorIs(t, err, signing.ErrInvalidConfig)
	})
}

func TestHandleMaxLengthCoversEverythingSealCanProduce(t *testing.T) {
	t.Parallel()

	// userIDMaxLength is 100 and encoding/json escapes '<' to six bytes,
	// so this is the longest identityKey a login can legally reach.
	sess := testSession()
	sess.IdentityKey = strings.Repeat("<", 100)
	sess.Generation = 1 << 30

	handle := reseal(t, newSigned(t, testKey(t, 1)), sess)
	t.Logf("worst-case handle is %d chars against a cap of %d", len(handle), authsessiontoken.HandleMaxLength)
	require.LessOrEqual(t, len(handle), authsessiontoken.HandleMaxLength,
		"the cap must clear the worst case Seal can produce, or login hands out handles Unseal rejects")

	_, err := newSigned(t, testKey(t, 1)).Unseal(context.Background(), handle)
	require.NoError(t, err)
}

func TestMillisecondPrecision(t *testing.T) {
	t.Parallel()

	// The payload carries milliseconds, so sub-millisecond precision is
	// lost. Round-tripping must be stable, or a resealed session's
	// deadlines would wobble.
	sess := testSession()
	sess.CreatedAt = testTime.Add(1234567 * time.Microsecond)
	sess.LineageIssuedAt = testTime.Add(7654321 * time.Microsecond)

	sealer := newSigned(t, testKey(t, 1))
	got, err := sealer.Unseal(context.Background(), reseal(t, sealer, sess))
	require.NoError(t, err)

	require.Equal(t, sess.CreatedAt.Truncate(time.Millisecond).UTC(), got.CreatedAt.UTC())
	require.Equal(t, sess.LineageIssuedAt.Truncate(time.Millisecond).UTC(), got.LineageIssuedAt.UTC())

	// And it is a fixed point: sealing what came back changes nothing.
	require.Equal(t, reseal(t, sealer, got), reseal(t, sealer, got))
}
