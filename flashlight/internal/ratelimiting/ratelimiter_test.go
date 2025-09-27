package ratelimiting

import (
	"net/http"
	"strings"
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
}

func TestIPKeyFunc(t *testing.T) {
	cases := []struct {
		remoteAddr string
		key        string
	}{
		{"123.123.123.123", "ip: 123.123.123.123"},
		// Port is stripped
		{"127.0.0.1:52123", "ip: 127.0.0.1"},
	}
	for _, c := range cases {
		t.Run(c.remoteAddr, func(t *testing.T) {
			request := &http.Request{RemoteAddr: c.remoteAddr}
			require.Equal(t, c.key, IPKeyFunc(request))
		})
	}
}

func TestUserIDKeyFunc(t *testing.T) {
	cases := []struct {
		userID string
		key    string
	}{
		// Standard user ids (uuid)
		{"743e61ad84344c4a995145763950b4bd", "user-id: 743e61ad84344c4a995145763950b4bd"},
		{"1025ff88-5234-4481-900b-f64ea190cf4e", "user-id: 1025ff88-5234-4481-900b-f64ea190cf4e"},
		// Custom user id
		{"my-id", "user-id: my-id"},
		// Weird case
		{"", "user-id: <missing>"},
		// User controlled input -> Long strings get truncated
		{strings.Repeat("1", 1000), "user-id: " + strings.Repeat("1", 50)},
	}
	for _, c := range cases {
		t.Run(c.userID, func(t *testing.T) {
			request := &http.Request{
				Header: http.Header{"X-User-Id": []string{c.userID}},
			}
			require.Equal(t, c.key, UserIDKeyFunc(request))
		})
	}
	t.Run("missing", func(t *testing.T) {
		request := &http.Request{}
		require.Equal(t, "user-id: <missing>", UserIDKeyFunc(request))
	})
}

func TestRequestBasedRateLimiter(t *testing.T) {
	var expectedKey string
	var allowed bool
	rateLimiter := &mockedRateLimiter{
		consumeFunc: func(key string) bool {
			t.Helper()
			require.Equal(t, expectedKey, key)
			return allowed
		},
	}
	requestRateLimiter := NewRequestBasedRateLimiter(rateLimiter, IPKeyFunc)

	expectedKey = "ip: 1.1.1.1"
	allowed = true
	require.True(t, requestRateLimiter.Consume(&http.Request{RemoteAddr: "1.1.1.1"}))
	require.True(t, requestRateLimiter.Consume(&http.Request{RemoteAddr: "1.1.1.1"}))
	allowed = false
	require.False(t, requestRateLimiter.Consume(&http.Request{RemoteAddr: "1.1.1.1"}))

	expectedKey = "ip: 2.1.1.1"
	allowed = true
	require.True(t, requestRateLimiter.Consume(&http.Request{RemoteAddr: "2.1.1.1"}))

	expectedKey = "ip: 1.1.1.1"
	allowed = false
	require.False(t, requestRateLimiter.Consume(&http.Request{RemoteAddr: "1.1.1.1"}))
}
