package signing_test

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/signing"
)

func testKey(t *testing.T, fill byte) []byte {
	t.Helper()
	key := make([]byte, signing.MinKeyLength)
	for i := range key {
		key[i] = fill
	}
	return key
}

func TestParseKeys(t *testing.T) {
	t.Parallel()

	valid := base64.StdEncoding.EncodeToString(testKey(t, 1))
	other := base64.StdEncoding.EncodeToString(testKey(t, 2))

	t.Run("parses keys in order, skipping blanks", func(t *testing.T) {
		t.Parallel()
		keys, err := signing.ParseKeys([]string{valid, "", "  ", other})
		require.NoError(t, err)
		require.Equal(t, [][]byte{testKey(t, 1), testKey(t, 2)}, keys)
	})

	t.Run("rejects an empty key list", func(t *testing.T) {
		t.Parallel()
		for _, keys := range [][]string{nil, {}, {""}, {"  "}} {
			_, err := signing.ParseKeys(keys)
			require.ErrorIs(t, err, signing.ErrInvalidConfig)
		}
	})

	t.Run("rejects keys that aren't base64", func(t *testing.T) {
		t.Parallel()
		_, err := signing.ParseKeys([]string{"not base64!"})
		require.ErrorIs(t, err, signing.ErrInvalidConfig)
	})

	t.Run("rejects short keys", func(t *testing.T) {
		t.Parallel()
		short := base64.StdEncoding.EncodeToString([]byte("too-short"))
		_, err := signing.ParseKeys([]string{short})
		require.ErrorIs(t, err, signing.ErrInvalidConfig)
	})

	t.Run("does not leak key material in the error", func(t *testing.T) {
		t.Parallel()
		_, err := signing.ParseKeys([]string{"c2VjcmV0-not-base64"})
		require.Error(t, err)
		require.NotContains(t, err.Error(), "c2VjcmV0")
	})

	t.Run("generated keys parse", func(t *testing.T) {
		t.Parallel()
		generated, err := signing.GenerateKey()
		require.NoError(t, err)
		keys, err := signing.ParseKeys([]string{generated})
		require.NoError(t, err)
		require.Len(t, keys, 1)
	})
}

func TestSign(t *testing.T) {
	t.Parallel()

	key := testKey(t, 1)

	t.Run("is HMAC-SHA256 over the body", func(t *testing.T) {
		t.Parallel()
		mac := hmac.New(sha256.New, key)
		_, err := mac.Write([]byte("body"))
		require.NoError(t, err)
		require.Equal(t, mac.Sum(nil), signing.Sign(key, "body"))
	})

	t.Run("differs by key and by body", func(t *testing.T) {
		t.Parallel()
		require.NotEqual(t, signing.Sign(key, "body"), signing.Sign(testKey(t, 2), "body"))
		require.NotEqual(t, signing.Sign(key, "body"), signing.Sign(key, "other"))
	})
}

func TestSignedByAnyKey(t *testing.T) {
	t.Parallel()

	first := testKey(t, 1)
	second := testKey(t, 2)
	stranger := testKey(t, 3)

	t.Run("accepts a signature from any key in the list", func(t *testing.T) {
		t.Parallel()
		keys := [][]byte{first, second}
		require.True(t, signing.SignedByAnyKey(keys, "body", signing.Sign(first, "body")))
		require.True(t, signing.SignedByAnyKey(keys, "body", signing.Sign(second, "body")))
	})

	t.Run("rejects a signature from a key that is not in the list", func(t *testing.T) {
		t.Parallel()
		require.False(t, signing.SignedByAnyKey([][]byte{first, second}, "body", signing.Sign(stranger, "body")))
	})

	t.Run("rejects a signature over a different body", func(t *testing.T) {
		t.Parallel()
		require.False(t, signing.SignedByAnyKey([][]byte{first}, "body", signing.Sign(first, "other")))
	})

	t.Run("rejects an empty key list", func(t *testing.T) {
		t.Parallel()
		require.False(t, signing.SignedByAnyKey(nil, "body", signing.Sign(first, "body")))
	})
}
