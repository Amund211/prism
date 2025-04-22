package cache

import "time"

type playerResponse struct {
	data       []byte
	statusCode int
}

type PlayerCache = Cache[playerResponse]

func NewTTLPlayerCache(ttl time.Duration) Cache[playerResponse] {
	return NewTTLCache[playerResponse](ttl)
}
