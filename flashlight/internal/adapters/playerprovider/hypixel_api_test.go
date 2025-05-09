package playerprovider

import (
	"bytes"
	"context"
	"io"
	"net/http"
	"reflect"
	"testing"
	"time"

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
	requestErr  error
}

func (m *mockedHttpClient) Do(req *http.Request) (*http.Response, error) {
	require.Equal(m.t, m.expectedURL, req.URL.String())
	require.True(m.t, reflect.DeepEqual(expectedHeaders, req.Header), "Expected %v, got %v", expectedHeaders, req.Header)

	return m.response, m.requestErr
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
		response: &http.Response{
			StatusCode: statusCode,
			Body:       io.NopCloser(bytes.NewBufferString(body)),
		},
		requestErr: err,
	}
}

func TestGetPlayerData(t *testing.T) {
	t.Run("success", func(t *testing.T) {
		httpClient := newMockedHttpClient(
			t,
			"https://api.hypixel.net/player?uuid=uuid1234",
			200,
			`{"success":true,"player":null}`,
			nil,
		)
		hypixelAPI := NewHypixelAPI(httpClient, apiKey)

		expectedQueriedAt := time.Now()

		data, statusCode, queriedAt, err := hypixelAPI.GetPlayerData(context.Background(), "uuid1234")

		require.Nil(t, err)
		require.Equal(t, 200, statusCode)
		require.Equal(t, `{"success":true,"player":null}`, string(data))
		require.WithinDuration(t, expectedQueriedAt, queriedAt, time.Second)
	})

	t.Run("request error", func(t *testing.T) {
		httpClient := newMockedHttpClient(
			t,
			"https://api.hypixel.net/player?uuid=uuid123456",
			200,
			`{"success":true,"player":null}`,
			assert.AnError,
		)
		hypixelAPI := NewHypixelAPI(httpClient, apiKey)

		_, _, _, err := hypixelAPI.GetPlayerData(context.Background(), "uuid123456")
		require.ErrorIs(t, err, assert.AnError)
	})

	t.Run("body read error", func(t *testing.T) {
		httpClient := &mockedHttpClient{
			t:           t,
			expectedURL: "https://api.hypixel.net/player?uuid=uuid",
			response: &http.Response{
				StatusCode: 200,
				Body:       cantRead{},
			},
			requestErr: nil,
		}
		hypixelAPI := NewHypixelAPI(httpClient, apiKey)

		_, _, _, err := hypixelAPI.GetPlayerData(context.Background(), "uuid")
		require.ErrorIs(t, err, assert.AnError)
	})
}
