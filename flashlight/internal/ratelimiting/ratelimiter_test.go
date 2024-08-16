package ratelimiting

import (
	"net/http"
	"runtime"
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

func TestKeyBasedRateLimiter(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping test in short mode")
	}
	rateLimiter := NewKeyBasedRateLimiter(1, 2)

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
