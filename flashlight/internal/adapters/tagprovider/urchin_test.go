package tagprovider_test

import (
	"bytes"
	"fmt"
	"io"
	"net/http"
	"reflect"
	"testing"
	"time"

	"github.com/Amund211/flashlight/internal/adapters/tagprovider"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/domaintest"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type mockedHttpClient struct {
	t           *testing.T
	expectedURL string
	response    *http.Response
	statusCode  int
	body        string
	err         error
}

func (m *mockedHttpClient) Do(req *http.Request) (*http.Response, error) {
	expectedHeaders := http.Header{
		// NOTE: go's http.Header automatically camelcases the keys
		"User-Agent": {"flashlight/0.1.0 (+https://github.com/Amund211/flashlight)"},
	}

	require.Equal(m.t, m.expectedURL, req.URL.String())
	require.True(m.t, reflect.DeepEqual(expectedHeaders, req.Header), "Expected %v, got %v", expectedHeaders, req.Header)

	if m.response != nil {
		return m.response, m.err
	}

	return &http.Response{
		StatusCode: m.statusCode,
		Body:       io.NopCloser(bytes.NewBufferString(m.body)),
	}, m.err
}

type cantRead struct{}

func (c cantRead) Read(p []byte) (n int, err error) {
	return 0, assert.AnError
}

func (c cantRead) Close() error {
	return nil
}

func TestUrchinTagsProvider(t *testing.T) {
	t.Parallel()

	now := time.Now()

	nowFunc := func() time.Time {
		return now
	}

	urlForUUID := func(uuid string) string {
		return fmt.Sprintf("https://urchin.ws/player/%s?sources=MANUAL", uuid)
	}

	uuid := domaintest.NewUUID(t)

	t.Run("success", func(t *testing.T) {
		t.Parallel()

		t.Run("empty tags", func(t *testing.T) {
			t.Parallel()
			httpClient := &mockedHttpClient{
				t:           t,
				expectedURL: urlForUUID(uuid),
				statusCode:  200,
				body:        `{"uuid":"0123456789abcdef0123456789abcdef","tags":[]}`,
				err:         nil,
			}
			urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After)
			require.NoError(t, err)

			tags, err := urchinAPI.GetTags(t.Context(), uuid, nil)
			require.NoError(t, err)

			require.Equal(t, domain.Tags{}, tags)
		})

		t.Run("sniper", func(t *testing.T) {
			t.Parallel()

			uuid := domaintest.NewUUID(t)

			httpClient := &mockedHttpClient{
				t:           t,
				expectedURL: urlForUUID(uuid),
				statusCode:  200,
				body:        `{"uuid":"0123456789abcdef0123456789abcdef","tags":[{"type":"sniper","reason":"3q - scaff, ab, blink","added_by_id":null,"added_by_username":null,"added_on":"2025-10-10T06:56:37.998405"}]}`,
				err:         nil,
			}
			urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After)
			require.NoError(t, err)

			tags, err := urchinAPI.GetTags(t.Context(), uuid, nil)
			require.NoError(t, err)

			require.Equal(
				t,
				domain.Tags{}.
					AddSniping(domain.TagSeverityHigh).
					AddCheating(domain.TagSeverityMedium),
				tags,
			)
		})

		t.Run("custom api key", func(t *testing.T) {
			t.Parallel()
			httpClient := &mockedHttpClient{
				t:           t,
				expectedURL: urlForUUID(uuid) + "&key=my-custom-key",
				statusCode:  200,
				body:        `{"uuid":"0123456789abcdef0123456789abcdef","tags":[]}`,
				err:         nil,
			}
			urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After)
			require.NoError(t, err)

			key := "my-custom-key"
			tags, err := urchinAPI.GetTags(t.Context(), uuid, &key)
			require.NoError(t, err)

			require.Equal(t, domain.Tags{}, tags)
		})
	})

	t.Run("error", func(t *testing.T) {
		t.Parallel()

		t.Run("status code", func(t *testing.T) {
			t.Parallel()
			// NOTE: Synthetic test
			httpClient := &mockedHttpClient{
				t:           t,
				expectedURL: urlForUUID(uuid),
				statusCode:  500,
				body:        `{"uuid":"0123456789abcdef0123456789abcdef","tags":[]}`,
				err:         nil,
			}
			urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After)
			require.NoError(t, err)

			_, err = urchinAPI.GetTags(t.Context(), uuid, nil)
			require.Error(t, err)
		})

		t.Run("invalid json", func(t *testing.T) {
			t.Parallel()
			// NOTE: Synthetic test
			httpClient := &mockedHttpClient{
				t:           t,
				expectedURL: urlForUUID(uuid),
				statusCode:  200,
				body:        `{"uuid":"0123456789abcdef0123456789abcdef","tags":"some-tag"}`,
				err:         nil,
			}
			urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After)
			require.NoError(t, err)

			_, err = urchinAPI.GetTags(t.Context(), uuid, nil)
			require.Error(t, err)
		})

		t.Run("Invalid api key response", func(t *testing.T) {
			t.Parallel()

			invalidKey := "1o23iu1o2i"

			// NOTE: Real response from urchin when an invalid API key is used
			httpClient := &mockedHttpClient{
				t:           t,
				expectedURL: urlForUUID(uuid) + "&key=" + invalidKey,
				statusCode:  200,
				body:        `"Invalid Key"`,
				err:         nil,
			}
			urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After)
			require.NoError(t, err)

			_, err = urchinAPI.GetTags(t.Context(), uuid, &invalidKey)
			require.ErrorIs(t, err, domain.ErrInvalidAPIKey)
		})

		t.Run("auth status code", func(t *testing.T) {
			t.Parallel()
			// NOTE: Synthetic test for 401/403 responses from urchin
			for _, statusCode := range []int{http.StatusUnauthorized, http.StatusForbidden} {
				t.Run(fmt.Sprintf("status code %d", statusCode), func(t *testing.T) {
					t.Parallel()

					invalidKey := "1o23iu1o2i"

					httpClient := &mockedHttpClient{
						t:           t,
						expectedURL: urlForUUID(uuid) + "&key=" + invalidKey,
						statusCode:  statusCode,
						body:        ``,
						err:         nil,
					}
					urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After)
					require.NoError(t, err)

					_, err = urchinAPI.GetTags(t.Context(), uuid, &invalidKey)
					require.ErrorIs(t, err, domain.ErrInvalidAPIKey)
				})
			}
		})

		t.Run("Invalid api key response when not passing API key", func(t *testing.T) {
			t.Parallel()

			httpClient := &mockedHttpClient{
				t:           t,
				expectedURL: urlForUUID(uuid),
				statusCode:  200,
				body:        `"Invalid Key"`,
				err:         nil,
			}
			urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After)
			require.NoError(t, err)

			_, err = urchinAPI.GetTags(t.Context(), uuid, nil)
			require.NotErrorIs(t, err, domain.ErrInvalidAPIKey)
		})

		t.Run("auth status code when not passing API key", func(t *testing.T) {
			t.Parallel()
			for _, statusCode := range []int{http.StatusUnauthorized, http.StatusForbidden} {
				t.Run(fmt.Sprintf("status code %d", statusCode), func(t *testing.T) {
					t.Parallel()

					httpClient := &mockedHttpClient{
						t:           t,
						expectedURL: urlForUUID(uuid),
						statusCode:  statusCode,
						body:        ``,
						err:         nil,
					}
					urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After)
					require.NoError(t, err)

					_, err = urchinAPI.GetTags(t.Context(), uuid, nil)
					require.NotErrorIs(t, err, domain.ErrInvalidAPIKey)
				})
			}
		})
	})

	t.Run("body read error", func(t *testing.T) {
		t.Parallel()

		httpClient := &mockedHttpClient{
			t:           t,
			expectedURL: urlForUUID(uuid),
			response: &http.Response{
				StatusCode: 200,
				Body:       cantRead{},
			},
			err: nil,
		}
		urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After)
		require.NoError(t, err)

		_, err = urchinAPI.GetTags(t.Context(), uuid, nil)
		require.Error(t, err)
		require.ErrorIs(t, err, assert.AnError)
	})
}
