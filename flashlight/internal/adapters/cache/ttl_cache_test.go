package cache

import (
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestTTLCache(t *testing.T) {
	t.Parallel()

	t.Run("Set and get", func(t *testing.T) {
		t.Parallel()

		cache := NewTTLCache[Data](1000 * time.Second)

		cache.set("key", "data")

		result := cache.getOrClaim("key")
		require.False(t, result.claimed, "Expected entry to exist")
		require.Equal(t, "data", result.data)
	})

	t.Run("getOrClaim claims when missing", func(t *testing.T) {
		t.Parallel()

		cache := NewTTLCache[Data](1000 * time.Second)

		result := cache.getOrClaim("key")
		require.True(t, result.claimed, "Expected entry to not exist and get claimed")

		result = cache.getOrClaim("key")
		require.False(t, result.claimed, "Expected entry to exist and not get claimed")
		require.False(t, result.valid, "Expected entry to be invalid")
	})

	t.Run("delete", func(t *testing.T) {
		t.Parallel()

		cache := NewTTLCache[Data](1000 * time.Second)
		cache.set("key", "data")

		cache.delete("key")

		result := cache.getOrClaim("key")
		require.True(t, result.claimed, "Expected to not find a value")
	})

	t.Run("delete missing entry", func(t *testing.T) {
		t.Parallel()

		cache := NewTTLCache[Data](1000 * time.Second)

		cache.delete("key")

		result := cache.getOrClaim("key")
		require.True(t, result.claimed, "Expected to not find a value")
	})

	t.Run("wait", func(t *testing.T) {
		t.Parallel()

		cache := NewTTLCache[Data](1000 * time.Second)
		cache.wait()
	})
}

func TestTTLCacheWithMaxSize(t *testing.T) {
	t.Parallel()

	t.Run("keeps entries within max size", func(t *testing.T) {
		t.Parallel()

		cache := NewTTLCacheWithMaxSize[Data](1000*time.Second, 2)

		cache.set("key1", "data1")
		cache.set("key2", "data2")

		result := cache.getOrClaim("key1")
		require.False(t, result.claimed, "Expected key1 to still exist")
		require.Equal(t, "data1", result.data)

		result = cache.getOrClaim("key2")
		require.False(t, result.claimed, "Expected key2 to still exist")
		require.Equal(t, "data2", result.data)
	})

	t.Run("evicts the least recently used entry when max size is exceeded", func(t *testing.T) {
		t.Parallel()

		cache := NewTTLCacheWithMaxSize[Data](1000*time.Second, 2)

		cache.set("key1", "data1")
		cache.set("key2", "data2")

		// Touch key1 so key2 is the least recently used
		result := cache.getOrClaim("key1")
		require.False(t, result.claimed, "Expected key1 to still exist")

		cache.set("key3", "data3")

		result = cache.getOrClaim("key3")
		require.False(t, result.claimed, "Expected key3 to exist")
		require.Equal(t, "data3", result.data)

		result = cache.getOrClaim("key1")
		require.False(t, result.claimed, "Expected key1 to still exist")
		require.Equal(t, "data1", result.data)

		result = cache.getOrClaim("key2")
		require.True(t, result.claimed, "Expected key2 to have been evicted")
	})
}
