package playerprovider

import (
	"bytes"
	"context"
	"io"
	"net/http"
	"reflect"
	"sync"
	"testing"
	"testing/synctest"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

const apiKey = "key"

var expectedHeaders = http.Header{
	// NOTE: go's http.Header automatically camelcases the keys
	"User-Agent": {"flashlight/0.1.0 (+https://github.com/Amund211/flashlight)"},
	"Api-Key":    {apiKey},
}

type mockedHttpClient struct {
	t           *testing.T
	expectedURL string
	response    *http.Response
	statusCode  int
	body        string
	requestErr  error
}

func (m *mockedHttpClient) Do(req *http.Request) (*http.Response, error) {
	require.Equal(m.t, m.expectedURL, req.URL.String())
	require.True(m.t, reflect.DeepEqual(expectedHeaders, req.Header), "Expected %v, got %v", expectedHeaders, req.Header)

	if m.response != nil {
		return m.response, m.requestErr
	}

	return &http.Response{
		StatusCode: m.statusCode,
		Body:       io.NopCloser(bytes.NewBufferString(m.body)),
	}, m.requestErr
}

type cantRead struct{}

func (c cantRead) Read(p []byte) (n int, err error) {
	return 0, assert.AnError
}

func (c cantRead) Close() error {
	return nil
}

func newMockedHttpClient(t *testing.T, expectedURL string, statusCode int, body string, err error) *mockedHttpClient {
	return &mockedHttpClient{
		t:           t,
		expectedURL: expectedURL,
		statusCode:  statusCode,
		body:        body,
		requestErr:  err,
	}
}

func TestGetPlayerData(t *testing.T) {
	t.Parallel()

	now := time.Now()

	nowFunc := func() time.Time {
		return now
	}

	t.Run("success", func(t *testing.T) {
		t.Parallel()

		httpClient := newMockedHttpClient(
			t,
			"https://api.hypixel.net/player?uuid=uuid1234",
			200,
			`{"success":true,"player":null}`,
			nil,
		)
		hypixelAPI, err := NewHypixelAPI(httpClient, nowFunc, time.After, apiKey)
		require.NoError(t, err)

		data, statusCode, queriedAt, err := hypixelAPI.GetPlayerData(t.Context(), "uuid1234")

		require.Nil(t, err)
		require.Equal(t, 200, statusCode)
		require.Equal(t, `{"success":true,"player":null}`, string(data))
		require.Equal(t, now, queriedAt)
	})

	t.Run("request error", func(t *testing.T) {
		t.Parallel()

		httpClient := newMockedHttpClient(
			t,
			"https://api.hypixel.net/player?uuid=uuid123456",
			200,
			`{"success":true,"player":null}`,
			assert.AnError,
		)
		hypixelAPI, err := NewHypixelAPI(httpClient, nowFunc, time.After, apiKey)
		require.NoError(t, err)

		_, _, _, err = hypixelAPI.GetPlayerData(t.Context(), "uuid123456")
		require.ErrorIs(t, err, assert.AnError)
	})

	t.Run("body read error", func(t *testing.T) {
		t.Parallel()

		httpClient := &mockedHttpClient{
			t:           t,
			expectedURL: "https://api.hypixel.net/player?uuid=uuid",
			response: &http.Response{
				StatusCode: 200,
				Body:       cantRead{},
			},
			requestErr: nil,
		}
		hypixelAPI, err := NewHypixelAPI(httpClient, nowFunc, time.After, apiKey)
		require.NoError(t, err)

		_, _, _, err = hypixelAPI.GetPlayerData(t.Context(), "uuid")
		require.ErrorIs(t, err, assert.AnError)
	})

	t.Run("rate limiting", func(t *testing.T) {
		t.Parallel()
		synctest.Test(t, func(t *testing.T) {
			start := time.Now()
			httpClient := newMockedHttpClient(
				t,
				"https://api.hypixel.net/player?uuid=uuid1234",
				200,
				`{"success":true,"player":null}`,
				nil,
			)
			hypixelAPI, err := NewHypixelAPI(httpClient, time.Now, time.After, apiKey)
			require.NoError(t, err)

			wg := sync.WaitGroup{}

			for range 600 {
				wg.Go(func() {
					data, statusCode, queriedAt, err := hypixelAPI.GetPlayerData(t.Context(), "uuid1234")
					require.NoError(t, err)
					require.Equal(t, 200, statusCode)
					require.Equal(t, `{"success":true,"player":null}`, string(data))
					require.Equal(t, start, queriedAt)
				})
			}
			wg.Wait()

			require.Equal(t, start, time.Now())

			ctxWithDeadline, cancel := context.WithTimeout(t.Context(), 10*time.Second)
			defer cancel()
			// Will have to wait for 5 minutes due to rate limiting -> should cancel
			_, _, _, err = hypixelAPI.GetPlayerData(ctxWithDeadline, "uuid1234")
			require.ErrorIs(t, err, domain.ErrTemporarilyUnavailable)

			require.Equal(t, start, time.Now())

			for range 600 {
				wg.Go(func() {
					data, statusCode, queriedAt, err := hypixelAPI.GetPlayerData(t.Context(), "uuid1234")
					require.NoError(t, err)
					require.Equal(t, 200, statusCode)
					require.Equal(t, `{"success":true,"player":null}`, string(data))
					require.Equal(t, start.Add(5*time.Minute), queriedAt)
				})
			}
			wg.Wait()

			require.Equal(t, start.Add(5*time.Minute), time.Now())

			data, statusCode, queriedAt, err := hypixelAPI.GetPlayerData(t.Context(), "uuid1234")
			require.NoError(t, err)
			require.Equal(t, 200, statusCode)
			require.Equal(t, `{"success":true,"player":null}`, string(data))
			require.Equal(t, start.Add(10*time.Minute), queriedAt)
		})
	})
}
