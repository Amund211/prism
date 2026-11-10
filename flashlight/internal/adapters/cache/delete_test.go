package cache

import (
	"fmt"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

// cacheImplementations is every Cache the tests below run against. Delete is
// called from a different goroutine than the GetOrCreate it races with, so
// each implementation's locking is what these tests are really about — run
// them under -race.
func cacheImplementations() []struct {
	name string
	make func() Cache[Data]
} {
	return []struct {
		name string
		make func() Cache[Data]
	}{
		{name: "BasicCache", make: func() Cache[Data] { return NewBasicCache[Data]() }},
		{name: "TTLCache", make: func() Cache[Data] { return NewTTLCacheWithMaxSize[Data](1*time.Minute, 1000) }},
	}
}

type getOrCreateResult struct {
	data    Data
	created bool
	err     error
}

func TestDelete(t *testing.T) {
	t.Parallel()

	for _, c := range cacheImplementations() {
		t.Run(c.name, func(t *testing.T) {
			t.Parallel()

			t.Run("removes the entry", func(t *testing.T) {
				t.Parallel()

				cache := c.make()

				_, created, err := GetOrCreate(t.Context(), cache, "key1", createCallback(1))
				require.NoError(t, err)
				require.True(t, created)

				Delete(cache, "key1")

				data, created, err := GetOrCreate(t.Context(), cache, "key1", createCallback(2))
				require.NoError(t, err)
				require.True(t, created, "the deleted entry must not be served")
				require.Equal(t, "data2", data)
			})

			t.Run("deleting a missing key is a no-op", func(t *testing.T) {
				t.Parallel()

				cache := c.make()

				Delete(cache, "key1")

				data, created, err := GetOrCreate(t.Context(), cache, "key1", createCallback(1))
				require.NoError(t, err)
				require.True(t, created)
				require.Equal(t, "data1", data)
			})

			t.Run("an in-flight create still returns, and repopulates the key", func(t *testing.T) {
				t.Parallel()

				// The documented limit of Delete: it cannot reach a create()
				// that already holds the claim. That caller must still finish
				// normally — the delete must not turn its set() into a panic
				// or make it report an error — and its value lands in the
				// cache afterwards, which is why callers delete only once
				// their write is durable.
				cache := c.make()

				started := make(chan struct{})
				release := make(chan struct{})
				results := make(chan getOrCreateResult, 1)

				go func() {
					data, created, err := GetOrCreate(t.Context(), cache, "key1", func() (Data, error) {
						close(started)
						<-release
						return createResponse(1)
					})
					results <- getOrCreateResult{data: data, created: created, err: err}
				}()

				<-started
				Delete(cache, "key1")
				close(release)

				result := <-results
				require.NoError(t, result.err)
				require.True(t, result.created)
				require.Equal(t, "data1", result.data)

				hit := cache.getOrClaim("key1")
				require.False(t, hit.claimed, "the creator's set must have landed")
				require.True(t, hit.valid)
				require.Equal(t, "data1", hit.data)
			})

			t.Run("a waiter behind the deleted claim creates instead of hanging", func(t *testing.T) {
				t.Parallel()

				// A caller that did not get the claim polls until the claimer
				// publishes or drops it. Deleting the claim out from under it
				// is the drop case: the waiter must take the claim itself and
				// create, not spin out its wait budget.
				cache := c.make()

				started := make(chan struct{})
				release := make(chan struct{})
				creatorResults := make(chan getOrCreateResult, 1)
				waiterResults := make(chan getOrCreateResult, 1)

				go func() {
					data, created, err := GetOrCreate(t.Context(), cache, "key1", func() (Data, error) {
						close(started)
						<-release
						return createResponse(1)
					})
					creatorResults <- getOrCreateResult{data: data, created: created, err: err}
				}()

				<-started

				go func() {
					data, created, err := GetOrCreate(t.Context(), cache, "key1", createCallback(2))
					waiterResults <- getOrCreateResult{data: data, created: created, err: err}
				}()

				Delete(cache, "key1")

				waiter := <-waiterResults
				require.NoError(t, waiter.err)
				require.True(t, waiter.created, "the waiter must have taken the freed claim")
				require.Equal(t, "data2", waiter.data)

				close(release)

				creator := <-creatorResults
				require.NoError(t, creator.err)
				require.Equal(t, "data1", creator.data)
			})

			t.Run("concurrent deletes and lookups", func(t *testing.T) {
				t.Parallel()

				// Deletes interleaved with claims, sets and hits on the same
				// keys, for the race detector to chew on. Every lookup must
				// come back with the key's value however the interleaving
				// falls — a delete may cost a repeat create, never a wrong
				// answer or a lost caller.
				ctx := t.Context()
				cache := c.make()

				wg := sync.WaitGroup{}
				for keyIndex := range 20 {
					key := fmt.Sprintf("key%d", keyIndex)
					want := fmt.Sprintf("data%d", keyIndex)

					for range 5 {
						wg.Go(func() {
							data, _, err := GetOrCreate(ctx, cache, key, func() (Data, error) {
								return want, nil
							})
							require.NoError(t, err)
							require.Equal(t, want, data)
						})
						wg.Go(func() {
							Delete(cache, key)
						})
					}
				}
				wg.Wait()
			})
		})
	}
}
