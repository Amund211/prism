package cache

import "time"

type PlayerResponse struct {
	Data       []byte
	StatusCode int
}

type PlayerCache = Cache[PlayerResponse]

func NewBasicPlayerCache() PlayerCache {
	return NewBasicCache[PlayerResponse]()
}

func NewTTLPlayerCache(ttl time.Duration) Cache[PlayerResponse] {
	return NewTTLCache[PlayerResponse](ttl)
}

var GetOrCreatePlayer = GetOrCreate[PlayerResponse]
