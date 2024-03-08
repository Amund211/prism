package cache

import (
	"fmt"
	"sync"
	"testing"

	"github.com/stretchr/testify/assert"
)

type Callback func() ([]byte, int, error)

func withWait(client *mockPlayerCacheClient, waits int, f Callback) Callback {
	wrapped := func() ([]byte, int, error) {
		for i := 0; i < waits; i++ {
			client.wait()
		}
		return f()
	}
	return wrapped
}

func createResponse(data int, statusCode int) ([]byte, int, error) {
	return []byte(fmt.Sprintf("data%d", data)), statusCode, nil
}

func createCallback(data int, statusCode int) Callback {
	return func() ([]byte, int, error) {
		return createResponse(data, statusCode)
	}
}

func createErrorCallback(variant int) Callback {
	return func() ([]byte, int, error) {
		return nil, -1, fmt.Errorf("error%d", variant)
	}
}

func createUnreachable(t *testing.T) Callback {
	return func() ([]byte, int, error) {
		t.Fatal("Unreachable code executed")
		return nil, -1, nil
	}
}

func TestMockedPlayerCacheFinishes(t *testing.T) {
	for clientCount := 0; clientCount < 10; clientCount++ {
		server, clients := NewMockPlayerCacheServer(clientCount, 100)
		completedWg := sync.WaitGroup{}
		completedWg.Add(clientCount)
		for i := 0; i < clientCount; i++ {
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
	server, clients := NewMockPlayerCacheServer(1, 10)

	go func() {
		client := clients[0]
		assert.Equal(t, 0, client.server.currentTick)

		data, statusCode, err := GetOrCreateCachedResponse(client, "uuid1", createCallback(1, 200))
		assert.Nil(t, err)
		assert.Equal(t, "data1", string(data))
		assert.Equal(t, 200, statusCode)
		assert.Equal(t, 0, client.server.currentTick)

		client.wait()

		assert.Equal(t, 1, client.server.currentTick)

		client.waitUntilDone()
	}()

	server.processTicks()
}

func TestGetOrCreateMultiple(t *testing.T) {
	server, clients := NewMockPlayerCacheServer(2, 10)

	go func() {
		client := clients[0]
		data, statusCode, err := GetOrCreateCachedResponse(client, "uuid1", createCallback(1, 200))
		assert.Nil(t, err)
		assert.Equal(t, "data1", string(data))
		assert.Equal(t, 200, statusCode)
		assert.Equal(t, 0, client.server.currentTick)

		data, statusCode, err = GetOrCreateCachedResponse(client, "uuid2", withWait(client, 2, createCallback(2, 201)))
		assert.Nil(t, err)
		assert.Equal(t, "data2", string(data))
		assert.Equal(t, 201, statusCode)
		assert.Equal(t, 2, client.server.currentTick)

		client.waitUntilDone()
	}()

	go func() {
		client := clients[1]
		client.wait() // Wait for the first client to populate the cache
		data, statusCode, err := GetOrCreateCachedResponse(client, "uuid1", createUnreachable(t))
		assert.Nil(t, err)
		assert.Equal(t, "data1", string(data))
		assert.Equal(t, 200, statusCode)
		assert.Equal(t, 1, client.server.currentTick)

		data, statusCode, err = GetOrCreateCachedResponse(client, "uuid2", createUnreachable(t))
		assert.Nil(t, err)
		assert.Equal(t, "data2", string(data))
		assert.Equal(t, 201, statusCode)
		// The fist client will insert this during the second tick
		// If our second tick processes after the first client's we will get it in the second tick
		// If our second tick processes before the first client's we will get it in the third tick
		assert.True(t, client.server.currentTick == 2 || client.server.currentTick == 3)

		client.waitUntilDone()
	}()

	server.processTicks()
}

func TestGetOrCreateErrorRetries(t *testing.T) {
	server, clients := NewMockPlayerCacheServer(2, 10)

	go func() {
		client := clients[0]
		_, _, err := GetOrCreateCachedResponse(client, "uuid1", withWait(client, 2, createErrorCallback(1)))
		assert.NotNil(t, err)
		assert.Equal(t, 2, client.server.currentTick)

		client.waitUntilDone()
	}()

	go func() {
		client := clients[1]
		client.wait()

		// This should wait for the first client to finish (not storing a result due to an error)
		// then it should retry and get the result
		data, statusCode, err := GetOrCreateCachedResponse(client, "uuid1", withWait(client, 2, createCallback(1, 200)))
		assert.Nil(t, err)
		assert.Equal(t, "data1", string(data))
		assert.Equal(t, 200, statusCode)
		assert.True(t, client.server.currentTick == 4 || client.server.currentTick == 5)

		client.waitUntilDone()
	}()

	server.processTicks()
}
