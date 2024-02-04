package cache

import (
    "github.com/jellydator/ttlcache/v3"
    "time"
    "log"
)


type cachedResponse struct {
	Data       []byte
	StatusCode int
	Valid      bool
}

type PlayerCache interface {
	getOrSet(uuid string, value cachedResponse) (cachedResponse, bool)
	Set(uuid string, data []byte, statusCode int, valid bool)
	Delete(uuid string)
	Wait()
}

type playerCacheImpl struct {
	cache *ttlcache.Cache[string, cachedResponse]
}

func (playerCache playerCacheImpl) getOrSet(uuid string, value cachedResponse) (cachedResponse, bool) {
	item, existed := playerCache.cache.GetOrSet(uuid, value)
	return item.Value(), existed
}

func (playerCache playerCacheImpl) Set(uuid string, data []byte, statusCode int, valid bool) {
	playerCache.cache.Set(uuid, cachedResponse{Data: data, StatusCode: statusCode, Valid: valid}, ttlcache.DefaultTTL)
}

func (playerCache playerCacheImpl) Delete(uuid string) {
	playerCache.cache.Delete(uuid)
}

func (playerCache playerCacheImpl) Wait() {
	time.Sleep(50 * time.Millisecond)
}

func NewPlayerCache(ttl time.Duration) PlayerCache {
	playerTTLCache := ttlcache.New[string, cachedResponse](
		ttlcache.WithTTL[string, cachedResponse](ttl),
		ttlcache.WithDisableTouchOnHit[string, cachedResponse](),
	)
	go playerTTLCache.Start()
	return playerCacheImpl{cache: playerTTLCache}
}

func GetOrCreateCachedResponse(playerCache PlayerCache, uuid string) cachedResponse {
	var value cachedResponse
	var existed bool
	var invalid = cachedResponse{Valid: false}

	for true {
		value, existed = playerCache.getOrSet(uuid, invalid)
		if !existed {
			// No entry existed, so we communicate to other requests that we are fetching data
			// Caller must defer playerCache.Delete(uuid) in case they fail
			log.Println("Got cache miss")
			return value
		}
		if value.Valid {
			// Cache hit
			log.Println("Got cache hit")
			return value
		}
		log.Println("Waiting for cache")
		playerCache.Wait()
	}
	panic("unreachable")
}

