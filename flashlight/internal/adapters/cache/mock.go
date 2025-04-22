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

func NewBasicPlayerCache() *basicCache[playerResponse] {
	return &basicCache[playerResponse]{
		cache: make(map[string]basicCacheEntry[playerResponse]),
	}
}

type mockPlayerCacheValue struct {
	cachedResponse basicCacheEntry[playerResponse]
	insertedAt     int
}

type mockPlayerCacheServer struct {
	cache             map[string]mockPlayerCacheValue
	lock              sync.Mutex
	currentTick       int
	maxTicks          int
	numGoroutines     int
	completedThisTick int
}

type mockPlayerCacheClient struct {
	server      *mockPlayerCacheServer
	desiredTick int
}

func (cacheClient *mockPlayerCacheClient) getOrClaim(uuid string) hitResult[playerResponse] {
	oldValue, ok := cacheClient.server.cache[uuid]
	if ok {
		return hitResult[playerResponse]{
			data:    oldValue.cachedResponse.data,
			valid:   oldValue.cachedResponse.valid,
			claimed: false,
		}
	}

	invalid := basicCacheEntry[playerResponse]{valid: false}
	cacheClient.server.cache[uuid] = mockPlayerCacheValue{cachedResponse: invalid, insertedAt: cacheClient.server.currentTick}
	return hitResult[playerResponse]{
		data:    invalid.data,
		valid:   invalid.valid,
		claimed: true,
	}
}

func (cacheClient *mockPlayerCacheClient) set(uuid string, data playerResponse) {
	cacheClient.server.cache[uuid] = mockPlayerCacheValue{cachedResponse: basicCacheEntry[playerResponse]{data: data, valid: true}, insertedAt: cacheClient.server.currentTick}
}

func (cacheClient *mockPlayerCacheClient) delete(uuid string) {
	delete(cacheClient.server.cache, uuid)
}

func (cacheClient *mockPlayerCacheClient) wait() {
	if cacheClient.server.isDone() {
		panic("wait() called on a client that is already done")
	}

	cacheClient.server.lock.Lock()
	cacheClient.server.completedThisTick++
	cacheClient.server.lock.Unlock()

	cacheClient.desiredTick++

	for cacheClient.server.currentTick < cacheClient.desiredTick {
		runtime.Gosched()
	}
}

func (cacheClient *mockPlayerCacheClient) waitUntilDone() {
	for !cacheClient.server.isDone() {
		cacheClient.wait()
	}
}

func (cacheServer *mockPlayerCacheServer) isDone() bool {
	return cacheServer.currentTick >= cacheServer.maxTicks
}

func (cacheServer *mockPlayerCacheServer) processTicks() {
	for !cacheServer.isDone() {
		if cacheServer.completedThisTick != cacheServer.numGoroutines {
			runtime.Gosched()
			continue
		}

		cacheServer.lock.Lock()
		cacheServer.completedThisTick = 0
		cacheServer.currentTick++
		cacheServer.lock.Unlock()
	}
}

func NewMockPlayerCacheServer(numGoroutines int, maxTicks int) (*mockPlayerCacheServer, []*mockPlayerCacheClient) {
	server := &mockPlayerCacheServer{
		cache:             make(map[string]mockPlayerCacheValue),
		lock:              sync.Mutex{},
		currentTick:       0,
		maxTicks:          maxTicks,
		numGoroutines:     numGoroutines,
		completedThisTick: 0,
	}

	clients := make([]*mockPlayerCacheClient, numGoroutines)
	for i := 0; i < numGoroutines; i++ {
		clients[i] = &mockPlayerCacheClient{
			server:      server,
			desiredTick: 0,
		}
	}

	return server, clients
}
