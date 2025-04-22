package cache

import (
	"runtime"
	"sync"
)

type basicCacheEntry[T any] struct {
	data  T
	valid bool
}

type basicCache[T any] struct {
	cache map[string]basicCacheEntry[T]
}

func (c *basicCache[T]) getOrClaim(key string) hitResult[T] {
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
	c.cache[key] = basicCacheEntry[T]{data: data, valid: true}
}

func (c *basicCache[T]) delete(key string) {
	delete(c.cache, key)
}

func (c *basicCache[T]) wait() {
}

func NewBasicCache[T any]() *basicCache[T] {
	return &basicCache[T]{
		cache: make(map[string]basicCacheEntry[T]),
	}
}

type mockCacheEntry[T any] struct {
	cachedResponse basicCacheEntry[T]
	insertedAt     int
}

type mockCacheServer[T any] struct {
	cache             map[string]mockCacheEntry[T]
	cacheLock         sync.Mutex
	tickLock          sync.Mutex
	currentTick       int
	maxTicks          int
	numGoroutines     int
	completedThisTick int
}

type mockCacheClient[T any] struct {
	server      *mockCacheServer[T]
	desiredTick int
}

func (cacheClient *mockCacheClient[T]) getOrClaim(uuid string) hitResult[T] {
	cacheClient.server.cacheLock.Lock()
	defer cacheClient.server.cacheLock.Unlock()

	oldValue, ok := cacheClient.server.cache[uuid]
	if ok {
		return hitResult[T]{
			data:    oldValue.cachedResponse.data,
			valid:   oldValue.cachedResponse.valid,
			claimed: false,
		}
	}

	invalid := basicCacheEntry[T]{valid: false}
	cacheClient.server.cache[uuid] = mockCacheEntry[T]{cachedResponse: invalid, insertedAt: cacheClient.server.currentTick}
	return hitResult[T]{
		data:    invalid.data,
		valid:   invalid.valid,
		claimed: true,
	}
}

func (cacheClient *mockCacheClient[T]) set(uuid string, data T) {
	cacheClient.server.cacheLock.Lock()
	defer cacheClient.server.cacheLock.Unlock()

	cacheClient.server.cache[uuid] = mockCacheEntry[T]{cachedResponse: basicCacheEntry[T]{data: data, valid: true}, insertedAt: cacheClient.server.currentTick}
}

func (cacheClient *mockCacheClient[T]) delete(uuid string) {
	cacheClient.server.cacheLock.Lock()
	defer cacheClient.server.cacheLock.Unlock()

	delete(cacheClient.server.cache, uuid)
}

func (cacheClient *mockCacheClient[T]) wait() {
	if cacheClient.server.isDone() {
		panic("wait() called on a client that is already done")
	}

	cacheClient.server.tickLock.Lock()
	cacheClient.server.completedThisTick++
	cacheClient.server.tickLock.Unlock()

	cacheClient.desiredTick++

	for cacheClient.server.currentTick < cacheClient.desiredTick {
		runtime.Gosched()
	}
}

func (cacheClient *mockCacheClient[T]) waitUntilDone() {
	for !cacheClient.server.isDone() {
		cacheClient.wait()
	}
}

func (cacheServer *mockCacheServer[T]) isDone() bool {
	return cacheServer.currentTick >= cacheServer.maxTicks
}

func (cacheServer *mockCacheServer[T]) processTicks() {
	for !cacheServer.isDone() {
		if cacheServer.completedThisTick != cacheServer.numGoroutines {
			runtime.Gosched()
			continue
		}

		cacheServer.tickLock.Lock()
		cacheServer.completedThisTick = 0
		cacheServer.currentTick++
		cacheServer.tickLock.Unlock()
	}
}

func NewMockCacheServer[T any](numGoroutines int, maxTicks int) (*mockCacheServer[T], []*mockCacheClient[T]) {
	server := &mockCacheServer[T]{
		cache:             make(map[string]mockCacheEntry[T]),
		tickLock:          sync.Mutex{},
		currentTick:       0,
		maxTicks:          maxTicks,
		numGoroutines:     numGoroutines,
		completedThisTick: 0,
	}

	clients := make([]*mockCacheClient[T], numGoroutines)
	for i := 0; i < numGoroutines; i++ {
		clients[i] = &mockCacheClient[T]{
			server:      server,
			desiredTick: 0,
		}
	}

	return server, clients
}
