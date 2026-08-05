package cache

import "context"

type hitResult[T any] struct {
	data    T
	valid   bool
	claimed bool
}

type Cache[T any] interface {
	getOrClaim(key string) hitResult[T]
	set(key string, data T)
	delete(key string)
	// wait blocks for a while before the caller retries getOrClaim.
	//
	// It must return early once ctx is done. GetOrCreate is the only caller,
	// and a waiter that keeps sleeping past its client's disconnect or
	// deadline holds a goroutine and a concurrency slot for a result nobody
	// will read.
	wait(ctx context.Context)
}
