package cache

import (
	"testing"
	"time"
)

func TestPlayerCacheImpl(t *testing.T) {
	t.Run("Set and get", func(t *testing.T) {
		t.Parallel()
		playerCache := NewPlayerCache(1000 * time.Second)

		playerCache.set("test", []byte("test"), 200)

		value, existed := playerCache.getOrSet("test", cachedResponse{})
		if !existed {
			t.Error("Expected entry to exist")
		}
		if string(value.data) != "test" {
			t.Errorf("Expected 'test', got %s", string(value.data))
		}
		if value.statusCode != 200 {
			t.Errorf("Expected 200, got %d", value.statusCode)
		}
	})

	t.Run("getOrSet sets when missing", func(t *testing.T) {
		t.Parallel()
		playerCache := NewPlayerCache(1000 * time.Second)

		value, existed := playerCache.getOrSet("test", cachedResponse{data: []byte("test"), statusCode: 200})
		if existed {
			t.Error("Expected entry to not exist")
		}
		if string(value.data) != "test" {
			t.Errorf("Expected 'test', got %s", string(value.data))
		}
		if value.statusCode != 200 {
			t.Errorf("Expected 200, got %d", value.statusCode)
		}
	})

	t.Run("delete", func(t *testing.T) {
		t.Parallel()
		playerCache := NewPlayerCache(1000 * time.Second)
		playerCache.set("test", []byte("test"), 200)

		playerCache.delete("test")

		_, existed := playerCache.getOrSet("test", cachedResponse{})
		if existed {
			t.Error("Expected to not find a value")
		}
	})

	t.Run("delete missing entry", func(t *testing.T) {
		t.Parallel()
		playerCache := NewPlayerCache(1000 * time.Second)

		playerCache.delete("test")

		_, existed := playerCache.getOrSet("test", cachedResponse{})
		if existed {
			t.Error("Expected to not find a value")
		}
	})

	t.Run("wait", func(t *testing.T) {
		t.Parallel()
		playerCache := NewPlayerCache(1000 * time.Second)
		playerCache.wait()
	})
}
