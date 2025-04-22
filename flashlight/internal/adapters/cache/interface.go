package cache

type cacheEntry[T any] struct {
	data  T
	valid bool
}

type Cache[T any] interface {
	getOrClaim(key string) (cacheEntry[T], bool)
	set(key string, data T)
	delete(key string)
	wait()
}

type playerResponse struct {
	data       []byte
	statusCode int
}

type playerCacheEntry = cacheEntry[playerResponse]
type PlayerCache = Cache[playerResponse]
