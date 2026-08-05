package cache

import (
	"context"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestTTLCache(t *testing.T) {
	t.Parallel()

	t.Run("Set and get", func(t *testing.T) {
		t.Parallel()

		cache := NewTTLCacheWithMaxSize[Data](1000*time.Second, 1000)

		cache.set("key", "data")

		result := cache.getOrClaim("key")
		require.False(t, result.claimed, "Expected entry to exist")
		require.Equal(t, "data", result.data)
	})

	t.Run("getOrClaim claims when missing", func(t *testing.T) {
		t.Parallel()

		cache := NewTTLCacheWithMaxSize[Data](1000*time.Second, 1000)

		result := cache.getOrClaim("key")
		require.True(t, result.claimed, "Expected entry to not exist and get claimed")

		result = cache.getOrClaim("key")
		require.False(t, result.claimed, "Expected entry to exist and not get claimed")
		require.False(t, result.valid, "Expected entry to be invalid")
	})

	t.Run("delete", func(t *testing.T) {
		t.Parallel()

		cache := NewTTLCacheWithMaxSize[Data](1000*time.Second, 1000)
		cache.set("key", "data")

		cache.delete("key")

		result := cache.getOrClaim("key")
		require.True(t, result.claimed, "Expected to not find a value")
	})

	t.Run("delete missing entry", func(t *testing.T) {
		t.Parallel()

		cache := NewTTLCacheWithMaxSize[Data](1000*time.Second, 1000)

		cache.delete("key")

		result := cache.getOrClaim("key")
		require.True(t, result.claimed, "Expected to not find a value")
	})

	t.Run("wait sleeps for the wait interval", func(t *testing.T) {
		t.Parallel()

		cache := &ttlCache[Data]{waitInterval: 20 * time.Millisecond}

		start := time.Now()
		cache.wait(t.Context())

		require.GreaterOrEqual(t, time.Since(start), 20*time.Millisecond)
	})

	t.Run("wait returns early when the context is already done", func(t *testing.T) {
		t.Parallel()

		// A wait interval far longer than any sane one, so that a wait
		// ignoring ctx fails the assertion rather than racing the clock.
		cache := &ttlCache[Data]{waitInterval: 10 * time.Second}

		ctx, cancel := context.WithCancel(t.Context())
		cancel()

		start := time.Now()
		cache.wait(ctx)

		require.Less(t, time.Since(start), 1*time.Second)
	})

	t.Run("wait returns when the context is cancelled while it waits", func(t *testing.T) {
		t.Parallel()

		cache := &ttlCache[Data]{waitInterval: 10 * time.Second}

		ctx, cancel := context.WithCancel(t.Context())
		timer := time.AfterFunc(10*time.Millisecond, cancel)
		defer timer.Stop()

		start := time.Now()
		cache.wait(ctx)

		require.Less(t, time.Since(start), 1*time.Second)
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
