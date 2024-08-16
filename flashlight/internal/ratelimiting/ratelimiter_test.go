package ratelimiting

import (
	"net/http"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

type mockedRateLimiter struct {
	consumeFunc func(key string) bool
}

func (m *mockedRateLimiter) Consume(key string) bool {
	return m.consumeFunc(key)
}

func TestTokenBucketRateLimiter(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping test in short mode")
	}
	rateLimiter := NewTokenBucketRateLimiter(RefillPerSecond(1), BurstSize(2))

	assert.True(t, rateLimiter.Consume("user2"))

	// Burst of 2
	assert.True(t, rateLimiter.Consume("user1"))
	assert.True(t, rateLimiter.Consume("user1"))
	assert.False(t, rateLimiter.Consume("user1"))

	time.Sleep(1000 * time.Millisecond)
	runtime.Gosched()

	// Refill rate of 1
	assert.True(t, rateLimiter.Consume("user1"))
	assert.False(t, rateLimiter.Consume("user1"))

	// Burst of 2 - even after refill
	assert.True(t, rateLimiter.Consume("user3"))
	assert.True(t, rateLimiter.Consume("user3"))
	assert.False(t, rateLimiter.Consume("user3"))

	assert.True(t, rateLimiter.Consume("user2"))
	assert.True(t, rateLimiter.Consume("user2"))
	assert.False(t, rateLimiter.Consume("user2"))
}

func TestIPKeyFunc(t *testing.T) {
	request := &http.Request{RemoteAddr: "123.123.123.123"}
	assert.Equal(t, "ip: 123.123.123.123", IPKeyFunc(request))
}

func TestUserIdKeyFunc(t *testing.T) {
	cases := []struct {
		userId string
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
		t.Run(c.userId, func(t *testing.T) {
			request := &http.Request{
				Header: http.Header{"X-User-Id": []string{c.userId}},
			}
			assert.Equal(t, c.key, UserIdKeyFunc(request))
		})
	}
	t.Run("missing", func(t *testing.T) {
		request := &http.Request{}
		assert.Equal(t, "user-id: <missing>", UserIdKeyFunc(request))
	})
}

func TestRequestBasedRateLimiter(t *testing.T) {
	var expectedKey string
	var allowed bool
	rateLimiter := &mockedRateLimiter{
		consumeFunc: func(key string) bool {
			t.Helper()
			assert.Equal(t, expectedKey, key)
			return allowed
		},
	}
	requestRateLimiter := NewRequestBasedRateLimiter(rateLimiter, IPKeyFunc)

	expectedKey = "ip: 1.1.1.1"
	allowed = true
	assert.True(t, requestRateLimiter.Consume(&http.Request{RemoteAddr: "1.1.1.1"}))
	assert.True(t, requestRateLimiter.Consume(&http.Request{RemoteAddr: "1.1.1.1"}))
	allowed = false
	assert.False(t, requestRateLimiter.Consume(&http.Request{RemoteAddr: "1.1.1.1"}))

	expectedKey = "ip: 2.1.1.1"
	allowed = true
	assert.True(t, requestRateLimiter.Consume(&http.Request{RemoteAddr: "2.1.1.1"}))

	expectedKey = "ip: 1.1.1.1"
	allowed = false
	assert.False(t, requestRateLimiter.Consume(&http.Request{RemoteAddr: "1.1.1.1"}))
}
