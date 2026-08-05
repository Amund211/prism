package cache

import (
	"context"
	"fmt"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

type Data = string

type Callback func() (Data, error)

func withWait[T any](client *mockCacheClient[T], waits int, f Callback) Callback {
	wrapped := func() (Data, error) {
		for range waits {
			client.wait(context.Background())
		}
		return f()
	}
	return wrapped
}

func createResponse(data int) (Data, error) {
	return fmt.Sprintf("data%d", data), nil
}

func createCallback(data int) Callback {
	return func() (Data, error) {
		return createResponse(data)
	}
}

func createErrorCallback(variant int) Callback {
	return func() (Data, error) {
		return "", fmt.Errorf("error%d", variant)
	}
}

func createUnreachable(t *testing.T) Callback {
	return func() (Data, error) {
		t.Fatal("Unreachable code executed")
		return "", nil
	}
}

func TestMockedCacheFinishes(t *testing.T) {
	t.Parallel()

	for clientCount := range 10 {
		server, clients := NewMockCacheServer[Data](clientCount, 100)
		completedWg := sync.WaitGroup{}
		completedWg.Add(clientCount)
		for i := range clientCount {
			go func() {
				client := clients[i]
				client.waitUntilDone()
				completedWg.Done()
			}()
		}
		server.processTicks()
		completedWg.Wait()
	}
}

func TestGetOrCreateSingle(t *testing.T) {
	t.Parallel()

	server, clients := NewMockCacheServer[Data](1, 10)

	go func() {
		client := clients[0]
		require.Equal(t, 0, int(client.server.currentTick.Load()))

		data, created, err := GetOrCreate(t.Context(), client, "key1", createCallback(1))
		require.Nil(t, err)
		require.True(t, created)
		require.Equal(t, "data1", data)
		require.Equal(t, 0, int(client.server.currentTick.Load()))

		client.wait(context.Background())

		require.Equal(t, 1, int(client.server.currentTick.Load()))

		client.waitUntilDone()
	}()

	server.processTicks()
}

func TestGetOrCreateMultiple(t *testing.T) {
	t.Parallel()

	server, clients := NewMockCacheServer[Data](2, 10)

	go func() {
		client := clients[0]
		data, created, err := GetOrCreate(t.Context(), client, "key1", createCallback(1))
		require.Nil(t, err)
		require.True(t, created)
		require.Equal(t, "data1", data)
		require.Equal(t, 0, int(client.server.currentTick.Load()))

		data, created, err = GetOrCreate(t.Context(), client, "key2", withWait(client, 2, createCallback(2)))
		require.Nil(t, err)
		require.True(t, created)
		require.Equal(t, "data2", data)
		require.Equal(t, 2, int(client.server.currentTick.Load()))

		client.waitUntilDone()
	}()

	go func() {
		client := clients[1]
		client.wait(context.Background()) // Wait for the first client to populate the cache
		data, created, err := GetOrCreate(t.Context(), client, "key1", createUnreachable(t))
		require.Nil(t, err)
		require.False(t, created)
		require.Equal(t, "data1", data)
		require.Equal(t, 1, int(client.server.currentTick.Load()))

		data, created, err = GetOrCreate(t.Context(), client, "key2", createUnreachable(t))
		require.Nil(t, err)
		require.False(t, created)
		require.Equal(t, "data2", data)
		// The fist client will insert this during the second tick
		// If our second tick processes after the first client's we will get it in the second tick
		// If our second tick processes before the first client's we will get it in the third tick
		require.True(t, int(client.server.currentTick.Load()) == 2 || int(client.server.currentTick.Load()) == 3)

		client.waitUntilDone()
	}()

	server.processTicks()
}

func TestGetOrCreateErrorRetries(t *testing.T) {
	t.Parallel()

	server, clients := NewMockCacheServer[Data](2, 10)

	go func() {
		client := clients[0]
		_, _, err := GetOrCreate(t.Context(), client, "key1", withWait(client, 2, createErrorCallback(1)))
		require.NotNil(t, err)
		require.Equal(t, 2, int(client.server.currentTick.Load()))

		client.waitUntilDone()
	}()

	go func() {
		client := clients[1]
		client.wait(context.Background())

		// This should wait for the first client to finish (not storing a result due to an error)
		// then it should retry and get the result
		data, created, err := GetOrCreate(t.Context(), client, "key1", withWait(client, 2, createCallback(1)))
		require.Nil(t, err)
		require.True(t, created)
		require.Equal(t, "data1", data)
		require.True(t, int(client.server.currentTick.Load()) == 4 || int(client.server.currentTick.Load()) == 5)

		client.waitUntilDone()
	}()

	server.processTicks()
}

func TestGetOrCreateCleansUpOnError(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name  string
		cache Cache[Data]
	}{
		{
			name:  "BasicCache",
			cache: NewBasicCache[Data](),
		},
		{
			name:  "TTLCache",
			cache: NewTTLCacheWithMaxSize[Data](1*time.Minute, 1000),
		},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			t.Parallel()

			_, _, err := GetOrCreate(t.Context(), c.cache, "key1", createErrorCallback(10))
			require.Error(t, err)

			// The cache should be empty and allow us to create a new entry
			data, created, err := GetOrCreate(t.Context(), c.cache, "key1", createCallback(1))
			require.Nil(t, err)
			require.True(t, created)
			require.Equal(t, "data1", data)
		})
	}
}

// TestGetOrCreateStopsWaiting covers the exits available to a caller that did
// not get the claim. Without them the loop only ends when the claimer
// publishes or fails, which no caller controls and neither the client nor the
// deadline can interrupt.
func TestGetOrCreateStopsWaiting(t *testing.T) {
	t.Parallel()

	t.Run("returns the context error when the context is already done", func(t *testing.T) {
		t.Parallel()

		c := NewBasicCache[Data]()
		// Somebody else holds the claim and never publishes
		require.True(t, c.getOrClaim("key1").claimed)

		ctx, cancel := context.WithCancel(t.Context())
		cancel()

		_, _, err := GetOrCreate(ctx, c, "key1", createUnreachable(t))
		require.ErrorIs(t, err, context.Canceled)
	})

	t.Run("does not create anything when the context is already done", func(t *testing.T) {
		t.Parallel()

		c := NewBasicCache[Data]()

		ctx, cancel := context.WithCancel(t.Context())
		cancel()

		// The entry is there for the taking, but nobody will read it
		_, _, err := GetOrCreate(ctx, c, "key1", createUnreachable(t))
		require.ErrorIs(t, err, context.Canceled)
	})

	t.Run("returns the context error when it is cancelled while waiting", func(t *testing.T) {
		t.Parallel()

		// The real wait, so this exercises a caller that is inside wait()
		// when the cancellation lands.
		c := NewTTLCacheWithMaxSize[Data](1*time.Minute, 1000)
		require.True(t, c.getOrClaim("key1").claimed)

		ctx, cancel := context.WithCancel(t.Context())
		timer := time.AfterFunc(10*time.Millisecond, cancel)
		defer timer.Stop()

		start := time.Now()
		_, _, err := GetOrCreate(ctx, c, "key1", createUnreachable(t))

		require.ErrorIs(t, err, context.Canceled)
		// Well short of the full budget of maxWaitAttempts * 50ms
		require.Less(t, time.Since(start), 5*time.Second)
	})

	t.Run("gives up once the wait budget is spent", func(t *testing.T) {
		t.Parallel()

		// basicCache's wait() doesn't sleep, so the whole budget is spent
		// without the test taking maxWaitAttempts * 50ms.
		c := NewBasicCache[Data]()
		require.True(t, c.getOrClaim("key1").claimed)

		_, _, err := GetOrCreate(t.Context(), c, "key1", createUnreachable(t))
		require.ErrorIs(t, err, ErrGaveUpWaiting)

		// Giving up must not take the other caller's claim with it — the
		// cleanup in GetOrCreate only applies to a claim we made ourselves.
		require.False(t, c.getOrClaim("key1").claimed)
	})

	t.Run("a waiter that gets the claim within the budget still creates", func(t *testing.T) {
		t.Parallel()

		// The real 50ms wait, so the claim below is dropped while this caller
		// is in its first wait rather than after the budget is gone.
		c := NewTTLCacheWithMaxSize[Data](1*time.Minute, 1000)
		require.True(t, c.getOrClaim("key1").claimed)

		// The claim is dropped a few attempts in, as it would be by a
		// create() that failed
		go func() {
			time.Sleep(10 * time.Millisecond)
			c.delete("key1")
		}()

		data, created, err := GetOrCreate(t.Context(), c, "key1", createCallback(1))
		require.NoError(t, err)
		require.True(t, created)
		require.Equal(t, "data1", data)
	})
}

func TestGetOrCreateRealCache(t *testing.T) {
	t.Parallel()

	t.Run("requests are de-duplicated in highly concurrent environment", func(t *testing.T) {
		t.Parallel()

		ctx := t.Context()
		cache := NewTTLCacheWithMaxSize[Data](1*time.Minute, 1000)

		wg := sync.WaitGroup{}

		for testIndex := range 100 {
			called := false
			monoStableCallback := func() (Data, error) {
				require.False(t, called, "Callback should only be called once")
				called = true
				return createResponse(1)
			}

			for range 10 {
				wg.Go(func() {
					data, _, err := GetOrCreate(ctx, cache, fmt.Sprintf("key%d", testIndex), monoStableCallback)
					require.NoError(t, err)
					// NOTE: We can't say anything about created here, as only one caller will create the entry
					require.Equal(t, "data1", data)
				})
			}
		}

		wg.Wait()
	})
}
