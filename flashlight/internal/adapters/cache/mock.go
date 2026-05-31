package cache

import (
	"runtime"
	"sync"
	"sync/atomic"
)

type mockCacheServerEntry[T any] struct {
	data       T
	valid      bool
	insertedAt int
}

type mockCacheServer[T any] struct {
	cache             map[string]mockCacheServerEntry[T]
	cacheLock         sync.Mutex
	currentTick       atomic.Int64
	maxTicks          int
	numGoroutines     int
	completedThisTick atomic.Int64
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
			data:    oldValue.data,
			valid:   oldValue.valid,
			claimed: false,
		}
	}

	cacheClient.server.cache[uuid] = mockCacheServerEntry[T]{
		valid:      false,
		insertedAt: int(cacheClient.server.currentTick.Load()),
	}
	return hitResult[T]{
		valid:   false,
		claimed: true,
	}
}

func (cacheClient *mockCacheClient[T]) set(uuid string, data T) {
	cacheClient.server.cacheLock.Lock()
	defer cacheClient.server.cacheLock.Unlock()

	cacheClient.server.cache[uuid] = mockCacheServerEntry[T]{
		data:       data,
		valid:      true,
		insertedAt: int(cacheClient.server.currentTick.Load()),
	}
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

	cacheClient.server.completedThisTick.Add(1)

	cacheClient.desiredTick++

	for cacheClient.server.currentTick.Load() < int64(cacheClient.desiredTick) {
		runtime.Gosched()
	}
}

func (cacheClient *mockCacheClient[T]) waitUntilDone() {
	for !cacheClient.server.isDone() {
		cacheClient.wait()
	}
}

func (cacheServer *mockCacheServer[T]) isDone() bool {
	return cacheServer.currentTick.Load() >= int64(cacheServer.maxTicks)
}

func (cacheServer *mockCacheServer[T]) processTicks() {
	for !cacheServer.isDone() {
		if cacheServer.completedThisTick.Load() != int64(cacheServer.numGoroutines) {
			runtime.Gosched()
			continue
		}

		cacheServer.completedThisTick.Store(0)
		cacheServer.currentTick.Add(1)
	}
}

func NewMockCacheServer[T any](numGoroutines int, maxTicks int) (*mockCacheServer[T], []*mockCacheClient[T]) {
	server := &mockCacheServer[T]{
		cache:         make(map[string]mockCacheServerEntry[T]),
		maxTicks:      maxTicks,
		numGoroutines: numGoroutines,
	}

	clients := make([]*mockCacheClient[T], numGoroutines)
	for i := range numGoroutines {
		clients[i] = &mockCacheClient[T]{
			server:      server,
			desiredTick: 0,
		}
	}

	return server, clients
}
