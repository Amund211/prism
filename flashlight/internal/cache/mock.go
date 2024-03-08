package cache

import (
	"runtime"
	"sync"
)

type mockCacheValue struct {
	cachedResponse cachedResponse
	insertedAt     int
}

type mockPlayerCacheServer struct {
	cache             map[string]mockCacheValue
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

func (cacheClient *mockPlayerCacheClient) getOrSet(uuid string, value cachedResponse) (cachedResponse, bool) {
	oldValue, ok := cacheClient.server.cache[uuid]
	if ok {
		return oldValue.cachedResponse, true
	}
	cacheClient.server.cache[uuid] = mockCacheValue{cachedResponse: value, insertedAt: cacheClient.server.currentTick}
	return value, false
}

func (cacheClient *mockPlayerCacheClient) set(uuid string, data []byte, statusCode int) {
	cacheClient.server.cache[uuid] = mockCacheValue{cachedResponse: cachedResponse{data: data, statusCode: statusCode, valid: true}, insertedAt: cacheClient.server.currentTick}
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
		cache:             make(map[string]mockCacheValue),
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
