package cache

type hitResult[T any] struct {
	data    T
	valid   bool
	claimed bool
}

type Cache[T any] interface {
	getOrClaim(key string) hitResult[T]
	set(key string, data T)
	delete(key string)
	wait()
}
