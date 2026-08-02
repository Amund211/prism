package proofofwork_test

import (
	"sync"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/proofofwork"
)

func TestInMemoryUsedNonceStore(t *testing.T) {
	t.Parallel()

	t.Run("a nonce can only be claimed once", func(t *testing.T) {
		t.Parallel()
		store, stop := proofofwork.NewInMemoryUsedNonceStore(100)
		t.Cleanup(stop)

		require.True(t, store.Claim("a"))
		require.False(t, store.Claim("a"))
		require.False(t, store.Claim("a"))
		require.True(t, store.Claim("b"))
	})

	t.Run("concurrent claims of one nonce produce a single winner", func(t *testing.T) {
		t.Parallel()
		store, stop := proofofwork.NewInMemoryUsedNonceStore(100)
		t.Cleanup(stop)

		// Two logins racing on the same solved challenge is exactly the
		// replay this store exists to stop, so the claim has to be atomic
		// rather than a read followed by a write.
		const racers = 32
		var (
			wg      sync.WaitGroup
			mutex   sync.Mutex
			winners int
		)
		wg.Add(racers)
		for range racers {
			go func() {
				defer wg.Done()
				if store.Claim("contended") {
					mutex.Lock()
					winners++
					mutex.Unlock()
				}
			}()
		}
		wg.Wait()

		require.Equal(t, 1, winners)
	})
}
