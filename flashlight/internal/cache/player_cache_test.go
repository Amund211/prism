package cache

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestPlayerCacheImpl(t *testing.T) {
	t.Run("Set and get", func(t *testing.T) {
		t.Parallel()
		playerCache := NewPlayerCache(1000 * time.Second)

		playerCache.set("test", []byte("test"), 200)

		value, existed := playerCache.getOrSet("test", cachedResponse{})
		assert.True(t, existed, "Expected entry to exist")
		assert.Equal(t, "test", string(value.data))
		assert.Equal(t, 200, value.statusCode)
	})

	t.Run("getOrSet sets when missing", func(t *testing.T) {
		t.Parallel()
		playerCache := NewPlayerCache(1000 * time.Second)

		value, existed := playerCache.getOrSet("test", cachedResponse{data: []byte("test"), statusCode: 200})
		assert.False(t, existed, "Expected entry to not exist")
		assert.Equal(t, "test", string(value.data))
		assert.Equal(t, 200, value.statusCode)
	})

	t.Run("delete", func(t *testing.T) {
		t.Parallel()
		playerCache := NewPlayerCache(1000 * time.Second)
		playerCache.set("test", []byte("test"), 200)

		playerCache.delete("test")

		_, existed := playerCache.getOrSet("test", cachedResponse{})
		assert.False(t, existed, "Expected to not find a value")
	})

	t.Run("delete missing entry", func(t *testing.T) {
		t.Parallel()
		playerCache := NewPlayerCache(1000 * time.Second)

		playerCache.delete("test")

		_, existed := playerCache.getOrSet("test", cachedResponse{})
		assert.False(t, existed, "Expected to not find a value")
	})

	t.Run("wait", func(t *testing.T) {
		t.Parallel()
		playerCache := NewPlayerCache(1000 * time.Second)
		playerCache.wait()
	})
}
