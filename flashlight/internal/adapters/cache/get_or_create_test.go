package cache

import (
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
			client.wait()
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
			i := i
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
		require.Equal(t, 0, client.server.currentTick)

		data, err := GetOrCreate(t.Context(), client, "key1", createCallback(1))
		require.Nil(t, err)
		require.Equal(t, "data1", string(data))
		require.Equal(t, 0, client.server.currentTick)

		client.wait()

		require.Equal(t, 1, client.server.currentTick)

		client.waitUntilDone()
	}()

	server.processTicks()
}

func TestGetOrCreateMultiple(t *testing.T) {
	t.Parallel()

	server, clients := NewMockCacheServer[Data](2, 10)

	go func() {
		client := clients[0]
		data, err := GetOrCreate(t.Context(), client, "key1", createCallback(1))
		require.Nil(t, err)
		require.Equal(t, "data1", string(data))
		require.Equal(t, 0, client.server.currentTick)

		data, err = GetOrCreate(t.Context(), client, "key2", withWait(client, 2, createCallback(2)))
		require.Nil(t, err)
		require.Equal(t, "data2", string(data))
		require.Equal(t, 2, client.server.currentTick)

		client.waitUntilDone()
	}()

	go func() {
		client := clients[1]
		client.wait() // Wait for the first client to populate the cache
		data, err := GetOrCreate(t.Context(), client, "key1", createUnreachable(t))
		require.Nil(t, err)
		require.Equal(t, "data1", string(data))
		require.Equal(t, 1, client.server.currentTick)

		data, err = GetOrCreate(t.Context(), client, "key2", createUnreachable(t))
		require.Nil(t, err)
		require.Equal(t, "data2", string(data))
		// The fist client will insert this during the second tick
		// If our second tick processes after the first client's we will get it in the second tick
		// If our second tick processes before the first client's we will get it in the third tick
		require.True(t, client.server.currentTick == 2 || client.server.currentTick == 3)

		client.waitUntilDone()
	}()

	server.processTicks()
}

func TestGetOrCreateErrorRetries(t *testing.T) {
	t.Parallel()

	server, clients := NewMockCacheServer[Data](2, 10)

	go func() {
		client := clients[0]
		_, err := GetOrCreate(t.Context(), client, "key1", withWait(client, 2, createErrorCallback(1)))
		require.NotNil(t, err)
		require.Equal(t, 2, client.server.currentTick)

		client.waitUntilDone()
	}()

	go func() {
		client := clients[1]
		client.wait()

		// This should wait for the first client to finish (not storing a result due to an error)
		// then it should retry and get the result
		data, err := GetOrCreate(t.Context(), client, "key1", withWait(client, 2, createCallback(1)))
		require.Nil(t, err)
		require.Equal(t, "data1", string(data))
		require.True(t, client.server.currentTick == 4 || client.server.currentTick == 5)

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
			cache: NewTTLCache[Data](1 * time.Minute),
		},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			t.Parallel()

			_, err := GetOrCreate(t.Context(), c.cache, "key1", createErrorCallback(10))
			require.Error(t, err)

			// The cache should be empty and allow us to create a new entry
			data, err := GetOrCreate(t.Context(), c.cache, "key1", createCallback(1))
			require.Nil(t, err)
			require.Equal(t, "data1", string(data))
		})
	}
}

func TestGetOrCreateRealCache(t *testing.T) {
	t.Parallel()

	t.Run("requests are de-duplicated in highly concurrent environment", func(t *testing.T) {
		t.Parallel()

		ctx := t.Context()
		cache := NewTTLCache[Data](1 * time.Minute)

		for testIndex := range 100 {
			t.Run(fmt.Sprintf("attempt #%d", testIndex), func(t *testing.T) {
				t.Parallel()

				called := false
				monoStableCallback := func() (Data, error) {
					require.False(t, called, "Callback should only be called once")
					called = true
					return createResponse(1)
				}

				for range 10 {
					go func() {
						data, err := GetOrCreate(ctx, cache, fmt.Sprintf("key%d", testIndex), monoStableCallback)
						require.Nil(t, err)
						require.Equal(t, "data1", string(data))
					}()
				}
			})
		}
	})
}
