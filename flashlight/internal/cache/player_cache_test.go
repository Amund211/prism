package cache

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestPlayerCacheImpl(t *testing.T) {
	t.Run("Set and get", func(t *testing.T) {
		playerCache := NewTTLPlayerCache(1000 * time.Second)

		playerCache.set("test", playerResponse{data: []byte("test"), statusCode: 200})

		value, claimed := playerCache.getOrClaim("test")
		assert.False(t, claimed, "Expected entry to exist")
		assert.Equal(t, "test", string(value.data.data))
		assert.Equal(t, 200, value.data.statusCode)
	})

	t.Run("getOrClaim claims when missing", func(t *testing.T) {
		playerCache := NewTTLPlayerCache(1000 * time.Second)

		value, claimed := playerCache.getOrClaim("test")
		assert.True(t, claimed, "Expected entry to not exist and get claimed")

		value, claimed = playerCache.getOrClaim("test")
		assert.False(t, claimed, "Expected entry to exist and not get claimed")
		assert.False(t, value.valid, "Expected entry to be invalid")
	})

	t.Run("delete", func(t *testing.T) {
		playerCache := NewTTLPlayerCache(1000 * time.Second)
		playerCache.set("test", playerResponse{data: []byte("test"), statusCode: 200})

		playerCache.delete("test")

		_, claimed := playerCache.getOrClaim("test")
		assert.True(t, claimed, "Expected to not find a value")
	})

	t.Run("delete missing entry", func(t *testing.T) {
		playerCache := NewTTLPlayerCache(1000 * time.Second)

		playerCache.delete("test")

		_, claimed := playerCache.getOrClaim("test")
		assert.True(t, claimed, "Expected to not find a value")
	})

	t.Run("wait", func(t *testing.T) {
		playerCache := NewTTLPlayerCache(1000 * time.Second)
		playerCache.wait()
	})
}
