package tagprovider_test

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"reflect"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/adapters/tagprovider"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/domaintest"
)

const defaultKey = "test-default-key"

type mockedHTTPClient struct {
	t              *testing.T
	expectedURL    string
	expectedAPIKey string
	response       *http.Response
	statusCode     int
	body           string
	err            error
}

func (m *mockedHTTPClient) Do(req *http.Request) (*http.Response, error) {
	expectedHeaders := http.Header{
		// NOTE: go's http.Header automatically camelcases the keys
		"User-Agent": {"flashlight/0.1.0 (+https://github.com/Amund211/flashlight)"},
		// The API key goes in a header, never in the URL
		"X-Api-Key": {m.expectedAPIKey},
	}

	require.Equal(m.t, m.expectedURL, req.URL.String())
	require.True(m.t, reflect.DeepEqual(expectedHeaders, req.Header), "Expected %v, got %v", expectedHeaders, req.Header)
	require.NotContains(m.t, req.URL.String(), m.expectedAPIKey, "API key must not appear in the URL")

	if m.response != nil {
		return m.response, m.err
	}

	return &http.Response{
		StatusCode: m.statusCode,
		Body:       io.NopCloser(bytes.NewBufferString(m.body)),
	}, m.err
}

type cantRead struct {
	err error
}

func (c *cantRead) Read(p []byte) (n int, err error) {
	return 0, c.err
}

func (c *cantRead) Close() error {
	return nil
}

func TestUrchinTagsProvider(t *testing.T) {
	t.Parallel()

	now := time.Now()

	nowFunc := func() time.Time {
		return now
	}

	urlForUUID := func(uuid string) string {
		return fmt.Sprintf("https://api.urchin.gg/v3/player/tags?player=%s", uuid)
	}

	uuid := domaintest.NewUUID(t)

	t.Run("success", func(t *testing.T) {
		t.Parallel()

		t.Run("empty tags", func(t *testing.T) {
			t.Parallel()
			// Real response from /v3/player/tags (2026-08-01) with the uuid anonymized.
			// displayname carries the rank prefix and its plus-colors.
			httpClient := &mockedHTTPClient{
				t:              t,
				expectedURL:    urlForUUID(uuid),
				expectedAPIKey: defaultKey,
				statusCode:     200,
				body:           `{"uuid":"0123456789abcdef0123456789abcdef","displayname":"§b[MVP§3+§b] Skydeath","tags":[]}`,
				err:            nil,
			}
			urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After, defaultKey)
			require.NoError(t, err)

			tags, err := urchinAPI.GetTags(t.Context(), uuid, nil)
			require.NoError(t, err)

			require.Equal(t, domain.Tags{}, tags)
		})

		t.Run("sniper", func(t *testing.T) {
			t.Parallel()

			uuid := domaintest.NewUUID(t)

			// Real tag object from POST /v3/players (2026-08-01), which returns no
			// displayname. `uuid`, `added_by` and `added_by_username` are anonymized.
			// See urchin_internal_test.go for the full set of parsing cases.
			httpClient := &mockedHTTPClient{
				t:              t,
				expectedURL:    urlForUUID(uuid),
				expectedAPIKey: defaultKey,
				statusCode:     200,
				body:           `{"uuid":"0123456789abcdef0123456789abcdef","tags":[{"tag_type":"sniper","reason":"ab legitscaff lagrange blink","added_by":111111111111111111,"added_by_username":"anonymized","added_on":1760968222172,"hide_username":false}]}`,
				err:            nil,
			}
			urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After, defaultKey)
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

		t.Run("custom api key overrides configured default", func(t *testing.T) {
			t.Parallel()

			key := "my-custom-key"

			httpClient := &mockedHTTPClient{
				t:              t,
				expectedURL:    urlForUUID(uuid),
				expectedAPIKey: key,
				statusCode:     200,
				body:           `{"uuid":"0123456789abcdef0123456789abcdef","tags":[]}`,
				err:            nil,
			}
			urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After, defaultKey)
			require.NoError(t, err)

			tags, err := urchinAPI.GetTags(t.Context(), uuid, &key)
			require.NoError(t, err)

			require.Equal(t, domain.Tags{}, tags)
		})

		t.Run("configured default api key is used when caller passes nil", func(t *testing.T) {
			t.Parallel()
			httpClient := &mockedHTTPClient{
				t:              t,
				expectedURL:    urlForUUID(uuid),
				expectedAPIKey: defaultKey,
				statusCode:     200,
				body:           `{"uuid":"0123456789abcdef0123456789abcdef","tags":[]}`,
				err:            nil,
			}
			urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After, defaultKey)
			require.NoError(t, err)

			tags, err := urchinAPI.GetTags(t.Context(), uuid, nil)
			require.NoError(t, err)

			require.Equal(t, domain.Tags{}, tags)
		})
	})

	t.Run("constructor requires non-empty default api key", func(t *testing.T) {
		t.Parallel()
		_, err := tagprovider.NewUrchin(&mockedHTTPClient{t: t}, nowFunc, time.After, "")
		require.Error(t, err)
	})

	t.Run("error", func(t *testing.T) {
		t.Parallel()

		t.Run("status code", func(t *testing.T) {
			t.Parallel()
			t.Run("429", func(t *testing.T) {
				// NOTE: Synthetic body - we have not captured a real v3 rate limit
				//       response. v3 documents errors as {"error": ...}, and the message
				//       text here is made up.
				httpClient := &mockedHTTPClient{
					t:              t,
					expectedURL:    urlForUUID(uuid),
					expectedAPIKey: defaultKey,
					statusCode:     429,
					body:           `{"error":"rate limit exceeded"}`,
					err:            nil,
				}
				urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After, defaultKey)
				require.NoError(t, err)

				_, err = urchinAPI.GetTags(t.Context(), uuid, nil)
				// Since we have experienced these intermittently, we allow the client to retry
				require.ErrorIs(t, err, domain.ErrTemporarilyUnavailable)
			})
			t.Run("500", func(t *testing.T) {
				// Real response from the pre-v3 urchin API (2025-11-18). Bodies like this
				// come from Cloudflare, which still fronts the v3 API.
				httpClient := &mockedHTTPClient{
					t:              t,
					expectedURL:    urlForUUID(uuid),
					expectedAPIKey: defaultKey,
					statusCode:     500,
					body:           `error code: 500`,
					err:            nil,
				}
				urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After, defaultKey)
				require.NoError(t, err)

				_, err = urchinAPI.GetTags(t.Context(), uuid, nil)
				// Since we have experienced these intermittently, we allow the client to retry
				require.ErrorIs(t, err, domain.ErrTemporarilyUnavailable)
			})
			t.Run("502", func(t *testing.T) {
				// Real response from the pre-v3 urchin API (2025-11-18). Bodies like this
				// come from Cloudflare, which still fronts the v3 API.
				httpClient := &mockedHTTPClient{
					t:              t,
					expectedURL:    urlForUUID(uuid),
					expectedAPIKey: defaultKey,
					statusCode:     502,
					body:           `error code: 502`,
					err:            nil,
				}
				urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After, defaultKey)
				require.NoError(t, err)

				_, err = urchinAPI.GetTags(t.Context(), uuid, nil)
				// Since we have experienced these intermittently, we allow the client to retry
				require.ErrorIs(t, err, domain.ErrTemporarilyUnavailable)
			})
			t.Run("503", func(t *testing.T) {
				// NOTE: Synthetic body - v3 documents 503 for "a service that Coral
				//       depends on is unavailable", but we have not captured a real one.
				httpClient := &mockedHTTPClient{
					t:              t,
					expectedURL:    urlForUUID(uuid),
					expectedAPIKey: defaultKey,
					statusCode:     503,
					body:           `{"error":"service unavailable"}`,
					err:            nil,
				}
				urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After, defaultKey)
				require.NoError(t, err)

				_, err = urchinAPI.GetTags(t.Context(), uuid, nil)
				require.ErrorIs(t, err, domain.ErrTemporarilyUnavailable)
			})
			t.Run("525", func(t *testing.T) {
				// Real response from the pre-v3 urchin API (2026-03-06). Cloudflare still
				// fronts the v3 API, so this remains reachable.
				httpClient := &mockedHTTPClient{
					t:              t,
					expectedURL:    urlForUUID(uuid),
					expectedAPIKey: defaultKey,
					statusCode:     525,
					body:           ``, // Sentry event had no data for this response
					err:            nil,
				}
				urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After, defaultKey)
				require.NoError(t, err)

				_, err = urchinAPI.GetTags(t.Context(), uuid, nil)
				// Since we have experienced these intermittently, we allow the client to retry
				require.ErrorIs(t, err, domain.ErrTemporarilyUnavailable)
			})
			t.Run("404", func(t *testing.T) {
				// Real response from /v3/player/tags (2026-08-01) for an identifier
				// urchin can't resolve. We normalize UUIDs before calling, so this
				// should not happen, and we let it surface as an error.
				httpClient := &mockedHTTPClient{
					t:              t,
					expectedURL:    urlForUUID(uuid),
					expectedAPIKey: defaultKey,
					statusCode:     404,
					body:           `{"error":"Player not found: not-a-uuid-!!"}`,
					err:            nil,
				}
				urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After, defaultKey)
				require.NoError(t, err)

				_, err = urchinAPI.GetTags(t.Context(), uuid, nil)
				require.Error(t, err)
				require.NotErrorIs(t, err, domain.ErrTemporarilyUnavailable)
			})
			t.Run("unexpected status code", func(t *testing.T) {
				// Made up response to test status codes we don't handle
				httpClient := &mockedHTTPClient{
					t:              t,
					expectedURL:    urlForUUID(uuid),
					expectedAPIKey: defaultKey,
					statusCode:     418,
					body:           `:^)`,
					err:            nil,
				}
				urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After, defaultKey)
				require.NoError(t, err)

				_, err = urchinAPI.GetTags(t.Context(), uuid, nil)
				require.Error(t, err)
				require.NotErrorIs(t, err, domain.ErrTemporarilyUnavailable)
			})
		})

		t.Run("http client errors", func(t *testing.T) {
			t.Parallel()
			t.Run("timeout while awaiting headers", func(t *testing.T) {
				t.Parallel()
				httpClient := &mockedHTTPClient{
					t:              t,
					expectedURL:    urlForUUID(uuid),
					expectedAPIKey: defaultKey,
					// Raw error string copied from sentry
					// NOTE: Error type is probably completely incorrect, but the text content
					//       (like from .Error()) should be correct
					err: errors.New(`Get "https://api.urchin.gg/v3/player/tags?player=0123456789abcdef0123456789abcdef": context deadline exceeded (Client.Timeout exceeded while awaiting headers)`),
				}
				urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After, defaultKey)
				require.NoError(t, err)

				_, err = urchinAPI.GetTags(t.Context(), uuid, nil)
				require.ErrorIs(t, err, domain.ErrTemporarilyUnavailable)
			})
			t.Run("context deadline exceeded", func(t *testing.T) {
				t.Parallel()
				// Newer net/http surfaces a context-deadline timeout without the
				// "Client.Timeout exceeded while awaiting headers" suffix; the wrapped
				// error is detectable via errors.Is(err, context.DeadlineExceeded).
				httpClient := &mockedHTTPClient{
					t:              t,
					expectedURL:    urlForUUID(uuid),
					expectedAPIKey: defaultKey,
					err: &url.Error{
						Op:  "Get",
						URL: urlForUUID(uuid),
						Err: context.DeadlineExceeded,
					},
				}
				urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After, defaultKey)
				require.NoError(t, err)

				_, err = urchinAPI.GetTags(t.Context(), uuid, nil)
				require.ErrorIs(t, err, domain.ErrTemporarilyUnavailable)
			})
			t.Run("connection reset by peer", func(t *testing.T) {
				t.Parallel()
				httpClient := &mockedHTTPClient{
					t:              t,
					expectedURL:    urlForUUID(uuid),
					expectedAPIKey: defaultKey,
					// Raw error string copied from sentry
					// NOTE: Error type is probably completely incorrect, but the text content
					//       (like from .Error()) should be correct
					err: errors.New(`Get "https://api.urchin.gg/v3/player/tags?player=0123456789abcdef0123456789abcdef": read tcp [ffff:ffff:ffff:ffff::ffff]:12345->[bbbb:bbbb:bbb:bbbb:bbbb:bbbb:bbbb:bbbb]:443: read: connection reset by peer`),
				}
				urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After, defaultKey)
				require.NoError(t, err)

				_, err = urchinAPI.GetTags(t.Context(), uuid, nil)
				require.ErrorIs(t, err, domain.ErrTemporarilyUnavailable)
			})
		})

		t.Run("invalid json", func(t *testing.T) {
			t.Parallel()
			// NOTE: Synthetic test
			httpClient := &mockedHTTPClient{
				t:              t,
				expectedURL:    urlForUUID(uuid),
				expectedAPIKey: defaultKey,
				statusCode:     200,
				body:           `{"uuid":"0123456789abcdef0123456789abcdef","tags":"some-tag"}`,
				err:            nil,
			}
			urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After, defaultKey)
			require.NoError(t, err)

			_, err = urchinAPI.GetTags(t.Context(), uuid, nil)
			require.Error(t, err)
			require.NotErrorIs(t, err, domain.ErrTemporarilyUnavailable)
		})

		t.Run("missing credentials response", func(t *testing.T) {
			t.Parallel()
			// Real response from /v3/player/tags (2026-08-01) when no key is sent at
			// all. We always send one, so this should not happen, and it is not a
			// caller error when it does.
			httpClient := &mockedHTTPClient{
				t:              t,
				expectedURL:    urlForUUID(uuid),
				expectedAPIKey: defaultKey,
				statusCode:     401,
				body:           `{"error":"missing credentials"}`,
				err:            nil,
			}
			urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After, defaultKey)
			require.NoError(t, err)

			_, err = urchinAPI.GetTags(t.Context(), uuid, nil)
			require.Error(t, err)
			require.NotErrorIs(t, err, domain.ErrInvalidAPIKey)
		})

		t.Run("auth status code", func(t *testing.T) {
			t.Parallel()
			// Both are real responses from v3 (2026-08-01), and both have an empty
			// body: 401 from /v3/player/tags with an unrecognized key, and 403 from a
			// v3 endpoint the key lacks permission for. A locked key also gives 403.
			for _, statusCode := range []int{http.StatusUnauthorized, http.StatusForbidden} {
				t.Run(fmt.Sprintf("status code %d", statusCode), func(t *testing.T) {
					t.Parallel()

					invalidKey := "1o23iu1o2i"

					httpClient := &mockedHTTPClient{
						t:              t,
						expectedURL:    urlForUUID(uuid),
						expectedAPIKey: invalidKey,
						statusCode:     statusCode,
						body:           ``,
						err:            nil,
					}
					urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After, defaultKey)
					require.NoError(t, err)

					_, err = urchinAPI.GetTags(t.Context(), uuid, &invalidKey)
					require.ErrorIs(t, err, domain.ErrInvalidAPIKey)
				})
			}
		})

		t.Run("auth status code when not passing API key", func(t *testing.T) {
			t.Parallel()
			// Same real responses as above, but with our own default key: a broken key
			// on our side must not be reported to the caller as their error.
			for _, statusCode := range []int{http.StatusUnauthorized, http.StatusForbidden} {
				t.Run(fmt.Sprintf("status code %d", statusCode), func(t *testing.T) {
					t.Parallel()

					httpClient := &mockedHTTPClient{
						t:              t,
						expectedURL:    urlForUUID(uuid),
						expectedAPIKey: defaultKey,
						statusCode:     statusCode,
						body:           ``,
						err:            nil,
					}
					urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After, defaultKey)
					require.NoError(t, err)

					_, err = urchinAPI.GetTags(t.Context(), uuid, nil)
					require.NotErrorIs(t, err, domain.ErrInvalidAPIKey)
				})
			}
		})
	})

	t.Run("body read error", func(t *testing.T) {
		t.Parallel()

		httpClient := &mockedHTTPClient{
			t:              t,
			expectedURL:    urlForUUID(uuid),
			expectedAPIKey: defaultKey,
			response: &http.Response{
				StatusCode: 200,
				Body:       &cantRead{err: assert.AnError},
			},
			err: nil,
		}
		urchinAPI, err := tagprovider.NewUrchin(httpClient, nowFunc, time.After, defaultKey)
		require.NoError(t, err)

		_, err = urchinAPI.GetTags(t.Context(), uuid, nil)
		require.Error(t, err)
		require.ErrorIs(t, err, assert.AnError)
	})
}
