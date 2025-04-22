package cache

import "sync"

type basicCacheEntry[T any] struct {
	data  T
	valid bool
}

type basicCache[T any] struct {
	cache     map[string]basicCacheEntry[T]
	cacheLock sync.Mutex
}

func (c *basicCache[T]) getOrClaim(key string) hitResult[T] {
	c.cacheLock.Lock()
	defer c.cacheLock.Unlock()

	oldValue, ok := c.cache[key]
	if ok {
		return hitResult[T]{
			data:    oldValue.data,
			valid:   oldValue.valid,
			claimed: false,
		}
	}

	c.cache[key] = basicCacheEntry[T]{valid: false}
	return hitResult[T]{
		valid:   false,
		claimed: true,
	}
}

func (c *basicCache[T]) set(key string, data T) {
	c.cacheLock.Lock()
	defer c.cacheLock.Unlock()

	c.cache[key] = basicCacheEntry[T]{data: data, valid: true}
}

func (c *basicCache[T]) delete(key string) {
	c.cacheLock.Lock()
	defer c.cacheLock.Unlock()

	delete(c.cache, key)
}

func (c *basicCache[T]) wait() {
}

func NewBasicCache[T any]() *basicCache[T] {
	return &basicCache[T]{
		cache: make(map[string]basicCacheEntry[T]),
	}
}
