package cache

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestPlayerCacheImpl(t *testing.T) {
	t.Run("Set and get", func(t *testing.T) {
		playerCache := NewTTLPlayerCache(1000 * time.Second)

		playerCache.set("test", PlayerResponse{Data: []byte("test"), StatusCode: 200})

		result := playerCache.getOrClaim("test")
		assert.False(t, result.claimed, "Expected entry to exist")
		assert.Equal(t, "test", string(result.data.Data))
		assert.Equal(t, 200, result.data.StatusCode)
	})

	t.Run("getOrClaim claims when missing", func(t *testing.T) {
		playerCache := NewTTLPlayerCache(1000 * time.Second)

		result := playerCache.getOrClaim("test")
		assert.True(t, result.claimed, "Expected entry to not exist and get claimed")

		result = playerCache.getOrClaim("test")
		assert.False(t, result.claimed, "Expected entry to exist and not get claimed")
		assert.False(t, result.valid, "Expected entry to be invalid")
	})

	t.Run("delete", func(t *testing.T) {
		playerCache := NewTTLPlayerCache(1000 * time.Second)
		playerCache.set("test", PlayerResponse{Data: []byte("test"), StatusCode: 200})

		playerCache.delete("test")

		result := playerCache.getOrClaim("test")
		assert.True(t, result.claimed, "Expected to not find a value")
	})

	t.Run("delete missing entry", func(t *testing.T) {
		playerCache := NewTTLPlayerCache(1000 * time.Second)

		playerCache.delete("test")

		result := playerCache.getOrClaim("test")
		assert.True(t, result.claimed, "Expected to not find a value")
	})

	t.Run("wait", func(t *testing.T) {
		playerCache := NewTTLPlayerCache(1000 * time.Second)
		playerCache.wait()
	})
}
