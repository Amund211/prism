package ratelimiting

import (
	"net/http"
	"testing"
	"testing/synctest"
	"time"

	"github.com/stretchr/testify/require"
)

type mockedRateLimiter struct {
	consumeFunc func(key string) bool
}

func (m *mockedRateLimiter) Consume(key string) bool {
	return m.consumeFunc(key)
}

func TestTokenBucketRateLimiter(t *testing.T) {
	t.Parallel()
	t.Run("basic", func(t *testing.T) {
		t.Parallel()
		synctest.Test(t, func(t *testing.T) {
			rateLimiter, stop := NewTokenBucketRateLimiter(RefillPerSecond(1), BurstSize(2))
			defer stop()

			require.True(t, rateLimiter.Consume("user2"))

			// Burst of 2
			require.True(t, rateLimiter.Consume("user1"))
			require.True(t, rateLimiter.Consume("user1"))
			require.False(t, rateLimiter.Consume("user1"))

			time.Sleep(1000 * time.Millisecond)

			// Refill rate of 1
			require.True(t, rateLimiter.Consume("user1"))
			require.False(t, rateLimiter.Consume("user1"))

			// Burst of 2 - even after refill
			require.True(t, rateLimiter.Consume("user3"))
			require.True(t, rateLimiter.Consume("user3"))
			require.False(t, rateLimiter.Consume("user3"))

			require.True(t, rateLimiter.Consume("user2"))
			require.True(t, rateLimiter.Consume("user2"))
			require.False(t, rateLimiter.Consume("user2"))
		})
	})

	t.Run("fractional refill", func(t *testing.T) {
		t.Parallel()
		synctest.Test(t, func(t *testing.T) {
			rateLimiter, stop := NewTokenBucketRateLimiter(RefillPerSecond(0.1), BurstSize(1))
			defer stop()

			require.True(t, rateLimiter.Consume("user1"))
			require.False(t, rateLimiter.Consume("user1"))

			for range 9 {
				time.Sleep(1000 * time.Millisecond)
				require.False(t, rateLimiter.Consume("user1"))
			}

			time.Sleep(1000 * time.Millisecond)
			require.True(t, rateLimiter.Consume("user1"))
		})
	})
}

func TestRequestBasedRateLimiter(t *testing.T) {
	t.Parallel()

	var expectedKey string
	var allowed bool
	rateLimiter := &mockedRateLimiter{
		consumeFunc: func(key string) bool {
			t.Helper()
			require.Equal(t, expectedKey, key)
			return allowed
		},
	}

	keyFunc := func(r *http.Request) string {
		return "ip: " + r.RemoteAddr
	}

	requestRateLimiter := NewRequestBasedRateLimiter(rateLimiter, keyFunc)

	expectedKey = "ip: 1.1.1.1"
	allowed = true
	require.True(t, requestRateLimiter.Consume(&http.Request{
		RemoteAddr: "1.1.1.1",
	}))
	require.True(t, requestRateLimiter.Consume(&http.Request{
		RemoteAddr: "1.1.1.1",
	}))
	allowed = false
	require.False(t, requestRateLimiter.Consume(&http.Request{
		RemoteAddr: "1.1.1.1",
	}))

	expectedKey = "ip: 2.1.1.1"
	allowed = true
	require.True(t, requestRateLimiter.Consume(&http.Request{
		RemoteAddr: "2.1.1.1",
	}))

	expectedKey = "ip: 1.1.1.1"
	allowed = false
	require.False(t, requestRateLimiter.Consume(&http.Request{
		RemoteAddr: "1.1.1.1",
	}))
}
