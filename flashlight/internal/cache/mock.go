package cache

import (
	"runtime"
	"sync"
)

type basicCache[T any] struct {
	cache map[string]cacheEntry[T]
}

func (c *basicCache[T]) getOrClaim(uuid string) (cacheEntry[T], bool) {
	oldValue, ok := c.cache[uuid]
	if ok {
		return oldValue, false
	}

	invalid := cacheEntry[T]{valid: false}
	c.cache[uuid] = invalid
	return invalid, true
}

func (c *basicCache[T]) set(uuid string, data T) {
	c.cache[uuid] = cacheEntry[T]{data: data, valid: true}
}

func (c *basicCache[T]) delete(uuid string) {
	delete(c.cache, uuid)
}

func (c *basicCache[T]) wait() {
}

func NewBasicPlayerCache() *basicCache[playerResponse] {
	return &basicCache[playerResponse]{
		cache: make(map[string]cacheEntry[playerResponse]),
	}
}

type mockPlayerCacheValue struct {
	cachedResponse cacheEntry[playerResponse]
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

func (cacheClient *mockPlayerCacheClient) getOrClaim(uuid string) (playerCacheEntry, bool) {
	oldValue, ok := cacheClient.server.cache[uuid]
	if ok {
		return oldValue.cachedResponse, false
	}

	invalid := playerCacheEntry{valid: false}
	cacheClient.server.cache[uuid] = mockPlayerCacheValue{cachedResponse: invalid, insertedAt: cacheClient.server.currentTick}
	return invalid, true
}

func (cacheClient *mockPlayerCacheClient) set(uuid string, data playerResponse) {
	cacheClient.server.cache[uuid] = mockPlayerCacheValue{cachedResponse: playerCacheEntry{data: data, valid: true}, insertedAt: cacheClient.server.currentTick}
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
