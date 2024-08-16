package ratelimiting

import (
	"runtime"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestKeyBasedRateLimiter(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping test in short mode")
	}
	rateLimiter := NewKeyBasedRateLimiter(1, 2)

	assert.True(t, rateLimiter.Allow("user2"))

	// Burst of 2
	assert.True(t, rateLimiter.Allow("user1"))
	assert.True(t, rateLimiter.Allow("user1"))
	assert.False(t, rateLimiter.Allow("user1"))

	time.Sleep(1000 * time.Millisecond)
	runtime.Gosched()

	// Refill rate of 1
	assert.True(t, rateLimiter.Allow("user1"))
	assert.False(t, rateLimiter.Allow("user1"))

	// Burst of 2 - even after refill
	assert.True(t, rateLimiter.Allow("user3"))
	assert.True(t, rateLimiter.Allow("user3"))
	assert.False(t, rateLimiter.Allow("user3"))

	assert.True(t, rateLimiter.Allow("user2"))
	assert.True(t, rateLimiter.Allow("user2"))
	assert.False(t, rateLimiter.Allow("user2"))
}
