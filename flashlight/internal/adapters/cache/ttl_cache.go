package cache

import (
	"time"

	"github.com/jellydator/ttlcache/v3"
)

type tllCacheEntry[T any] struct {
	data  T
	valid bool
}

type ttlCache[T any] struct {
	cache *ttlcache.Cache[string, tllCacheEntry[T]]
}

func (c *ttlCache[T]) getOrClaim(key string) hitResult[T] {
	invalid := tllCacheEntry[T]{valid: false}
	item, existed := c.cache.GetOrSet(key, invalid)

	// Snapshot the value once: a concurrent set() updates the underlying
	// *Item in place, so reading item.Value() twice can tear (e.g. observe
	// the old empty data together with the new valid=true).
	value := item.Value()

	return hitResult[T]{
		data:    value.data,
		valid:   value.valid,
		claimed: !existed,
	}
}

func (c *ttlCache[T]) set(key string, data T) {
	c.cache.Set(key, tllCacheEntry[T]{data: data, valid: true}, ttlcache.DefaultTTL)
}

func (c *ttlCache[T]) delete(key string) {
	c.cache.Delete(key)
}

func (c *ttlCache[T]) wait() {
	time.Sleep(50 * time.Millisecond)
}

func NewTTLCache[T any](ttl time.Duration) Cache[T] {
	cache := ttlcache.New[string, tllCacheEntry[T]](
		ttlcache.WithTTL[string, tllCacheEntry[T]](ttl),
		ttlcache.WithDisableTouchOnHit[string, tllCacheEntry[T]](),
	)
	go cache.Start()
	return &ttlCache[T]{cache: cache}
}
