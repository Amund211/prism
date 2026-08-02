package proofofwork

import (
	"github.com/jellydator/ttlcache/v3"
)

// UsedNonceStore records the nonces of challenges that have already been
// spent. It is the one piece of state in an otherwise stateless scheme,
// and the only thing standing between a solved challenge and unlimited
// sessions within its TTL.
type UsedNonceStore interface {
	// Claim marks nonce as used, reporting whether it was unused until now.
	Claim(nonce string) bool
}

type inMemoryUsedNonceStore struct {
	cache *ttlcache.Cache[string, struct{}]
}

func (s *inMemoryUsedNonceStore) Claim(nonce string) bool {
	_, existed := s.cache.GetOrSet(nonce, struct{}{})
	return !existed
}

// NewInMemoryUsedNonceStore returns a used-nonce set bounded by maxSize,
// along with the stop func for its eviction goroutine.
//
// In-memory means the bound is per instance: a solved challenge can be
// spent once per instance holding its own set. cmd/service.tmpl.yaml pins
// maxScale: 1, but that is per *revision*, so during a rollout the
// outgoing and incoming revisions both serve and a challenge is worth two
// sessions for the length of that window. Accepted — the window is short
// and the payoff is one extra anonymous identity — but it is the reason
// this wants Redis or an equivalent before flashlight genuinely scales out
// rather than after.
//
// Entries live for exactly the challenge TTL. An entry is written no
// earlier than its challenge's issued_at, so it always outlives the window
// in which that challenge can be presented. Under enough load to fill
// maxSize within one TTL the cache evicts least-recently-used entries and
// a replay could slip through; the login limiter bounds arrivals orders of
// magnitude below that.
func NewInMemoryUsedNonceStore(maxSize uint64) (UsedNonceStore, func()) {
	cache := ttlcache.New(
		ttlcache.WithTTL[string, struct{}](challengeTTL),
		// A repeated claim must not extend the entry's life; the challenge
		// it belongs to has a fixed deadline of its own.
		ttlcache.WithDisableTouchOnHit[string, struct{}](),
		ttlcache.WithCapacity[string, struct{}](maxSize),
	)
	go cache.Start()
	return &inMemoryUsedNonceStore{cache: cache}, cache.Stop
}
