package cache

import (
	"time"

	"github.com/jellydator/ttlcache/v3"
)

type ttlCache[T any] struct {
	cache *ttlcache.Cache[string, cacheEntry[T]]
}

func (c *ttlCache[T]) getOrClaim(uuid string) (cacheEntry[T], bool) {
	invalid := cacheEntry[T]{valid: false}
	item, existed := c.cache.GetOrSet(uuid, invalid)
	return item.Value(), !existed
}

func (c *ttlCache[T]) set(uuid string, data T) {
	c.cache.Set(uuid, cacheEntry[T]{data: data, valid: true}, ttlcache.DefaultTTL)
}

func (c *ttlCache[T]) delete(uuid string) {
	c.cache.Delete(uuid)
}

func (c *ttlCache[T]) wait() {
	time.Sleep(50 * time.Millisecond)
}

func NewTTLPlayerCache(ttl time.Duration) Cache[playerResponse] {
	playerTTLCache := ttlcache.New[string, cacheEntry[playerResponse]](
		ttlcache.WithTTL[string, cacheEntry[playerResponse]](ttl),
		ttlcache.WithDisableTouchOnHit[string, cacheEntry[playerResponse]](),
	)
	go playerTTLCache.Start()
	return &ttlCache[playerResponse]{cache: playerTTLCache}
}
