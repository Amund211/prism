package app_test

import (
	"context"
	"testing"

	"github.com/Amund211/flashlight/internal/adapters/cache"
	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type mockTagProvider struct {
	t *testing.T

	getTagsUUID   string
	getTagsAPIKey *string
	getTagsCalled bool
	getTagsTags   domain.Tags
	getTagsErr    error
}

func (m *mockTagProvider) GetTags(ctx context.Context, uuid string, apiKey *string) (domain.Tags, error) {
	m.t.Helper()
	require.Equal(m.t, m.getTagsUUID, uuid)

	if m.getTagsAPIKey == nil {
		require.Nil(m.t, apiKey)
	} else {
		require.NotNil(m.t, apiKey)
		require.Equal(m.t, *m.getTagsAPIKey, *apiKey)
	}

	require.False(m.t, m.getTagsCalled)

	m.getTagsCalled = true
	return m.getTagsTags, m.getTagsErr
}

func TestBuildGetTagsWithCache(t *testing.T) {
	t.Parallel()

	ctx := t.Context()
	UUID := "12345678-1234-1234-1234-123456789012"

	t.Run("call to provider without API key", func(t *testing.T) {
		t.Parallel()

		c := cache.NewBasicCache[domain.Tags]()
		provider := &mockTagProvider{
			t:             t,
			getTagsUUID:   UUID,
			getTagsAPIKey: nil,
			getTagsTags: domain.Tags{
				Cheating: domain.TagSeverityHigh,
				Sniping:  domain.TagSeverityMedium,
			},
		}
		getTagsWithCache, err := app.BuildGetTagsWithCache(c, provider)
		require.NoError(t, err)

		tags, err := getTagsWithCache(ctx, UUID, nil)
		require.NoError(t, err)
		require.Equal(t, domain.Tags{
			Cheating: domain.TagSeverityHigh,
			Sniping:  domain.TagSeverityMedium,
		}, tags)

		require.True(t, provider.getTagsCalled)
	})

	t.Run("call to provider with API key", func(t *testing.T) {
		t.Parallel()

		c := cache.NewBasicCache[domain.Tags]()
		apiKey := "test-api-key-12345"
		provider := &mockTagProvider{
			t:             t,
			getTagsUUID:   UUID,
			getTagsAPIKey: &apiKey,
			getTagsTags: domain.Tags{
				Cheating: domain.TagSeverityNone,
				Sniping:  domain.TagSeverityHigh,
			},
		}
		getTagsWithCache, err := app.BuildGetTagsWithCache(c, provider)
		require.NoError(t, err)

		tags, err := getTagsWithCache(ctx, UUID, &apiKey)
		require.NoError(t, err)
		require.Equal(t, domain.Tags{
			Cheating: domain.TagSeverityNone,
			Sniping:  domain.TagSeverityHigh,
		}, tags)

		require.True(t, provider.getTagsCalled)
	})

	t.Run("error in provider get results in error", func(t *testing.T) {
		t.Parallel()

		c := cache.NewBasicCache[domain.Tags]()
		provider := &mockTagProvider{
			t:             t,
			getTagsUUID:   UUID,
			getTagsAPIKey: nil,
			getTagsErr:    assert.AnError,
		}
		getTagsWithCache, err := app.BuildGetTagsWithCache(c, provider)
		require.NoError(t, err)

		_, err = getTagsWithCache(ctx, UUID, nil)
		require.ErrorIs(t, err, assert.AnError)

		require.True(t, provider.getTagsCalled)
	})

	t.Run("cache hit results in no calls", func(t *testing.T) {
		t.Parallel()

		c := cache.NewBasicCache[domain.Tags]()
		provider := &mockTagProvider{
			t:             t,
			getTagsUUID:   UUID,
			getTagsAPIKey: nil,
			getTagsTags: domain.Tags{
				Cheating: domain.TagSeverityMedium,
				Sniping:  domain.TagSeverityNone,
			},
		}
		getTagsWithCache, err := app.BuildGetTagsWithCache(c, provider)
		require.NoError(t, err)

		tags, err := getTagsWithCache(ctx, UUID, nil)
		require.NoError(t, err)
		require.Equal(t, domain.Tags{
			Cheating: domain.TagSeverityMedium,
			Sniping:  domain.TagSeverityNone,
		}, tags)

		provider = &mockTagProvider{
			t: t,
		}
		getTagsWithCache, err = app.BuildGetTagsWithCache(c, provider)
		require.NoError(t, err)

		tags, err = getTagsWithCache(ctx, UUID, nil)
		require.NoError(t, err)
		require.Equal(t, domain.Tags{
			Cheating: domain.TagSeverityMedium,
			Sniping:  domain.TagSeverityNone,
		}, tags)

		// We should have hit the cache, so no calls to provider
		require.False(t, provider.getTagsCalled)
	})

	t.Run("invalid UUID results in error", func(t *testing.T) {
		t.Parallel()

		c := cache.NewBasicCache[domain.Tags]()
		provider := &mockTagProvider{
			t: t,
		}
		getTagsWithCache, err := app.BuildGetTagsWithCache(c, provider)
		require.NoError(t, err)

		_, err = getTagsWithCache(ctx, "invalid-uuid", nil)
		require.Error(t, err)
		require.Contains(t, err.Error(), "UUID is not normalized")

		require.False(t, provider.getTagsCalled)
	})

	t.Run("different API keys result in different cache entries", func(t *testing.T) {
		t.Parallel()

		c := cache.NewBasicCache[domain.Tags]()
		apiKey1 := "api-key-1"
		apiKey2 := "api-key-2"

		// First call with apiKey1
		provider := &mockTagProvider{
			t:             t,
			getTagsUUID:   UUID,
			getTagsAPIKey: &apiKey1,
			getTagsTags: domain.Tags{
				Cheating: domain.TagSeverityHigh,
				Sniping:  domain.TagSeverityNone,
			},
		}
		getTagsWithCache, err := app.BuildGetTagsWithCache(c, provider)
		require.NoError(t, err)

		tags, err := getTagsWithCache(ctx, UUID, &apiKey1)
		require.NoError(t, err)
		require.Equal(t, domain.Tags{
			Cheating: domain.TagSeverityHigh,
			Sniping:  domain.TagSeverityNone,
		}, tags)
		require.True(t, provider.getTagsCalled)

		// Second call with apiKey2 should call provider again
		provider = &mockTagProvider{
			t:             t,
			getTagsUUID:   UUID,
			getTagsAPIKey: &apiKey2,
			getTagsTags: domain.Tags{
				Cheating: domain.TagSeverityMedium,
				Sniping:  domain.TagSeverityHigh,
			},
		}
		getTagsWithCache, err = app.BuildGetTagsWithCache(c, provider)
		require.NoError(t, err)

		tags, err = getTagsWithCache(ctx, UUID, &apiKey2)
		require.NoError(t, err)
		require.Equal(t, domain.Tags{
			Cheating: domain.TagSeverityMedium,
			Sniping:  domain.TagSeverityHigh,
		}, tags)
		require.True(t, provider.getTagsCalled)
	})

	t.Run("no API key and with API key result in different cache entries", func(t *testing.T) {
		t.Parallel()

		c := cache.NewBasicCache[domain.Tags]()
		apiKey := "api-key-test"

		// First call without API key
		provider := &mockTagProvider{
			t:             t,
			getTagsUUID:   UUID,
			getTagsAPIKey: nil,
			getTagsTags: domain.Tags{
				Cheating: domain.TagSeverityNone,
				Sniping:  domain.TagSeverityNone,
			},
		}
		getTagsWithCache, err := app.BuildGetTagsWithCache(c, provider)
		require.NoError(t, err)

		tags, err := getTagsWithCache(ctx, UUID, nil)
		require.NoError(t, err)
		require.Equal(t, domain.Tags{
			Cheating: domain.TagSeverityNone,
			Sniping:  domain.TagSeverityNone,
		}, tags)
		require.True(t, provider.getTagsCalled)

		// Second call with API key should call provider again
		provider = &mockTagProvider{
			t:             t,
			getTagsUUID:   UUID,
			getTagsAPIKey: &apiKey,
			getTagsTags: domain.Tags{
				Cheating: domain.TagSeverityHigh,
				Sniping:  domain.TagSeverityMedium,
			},
		}
		getTagsWithCache, err = app.BuildGetTagsWithCache(c, provider)
		require.NoError(t, err)

		tags, err = getTagsWithCache(ctx, UUID, &apiKey)
		require.NoError(t, err)
		require.Equal(t, domain.Tags{
			Cheating: domain.TagSeverityHigh,
			Sniping:  domain.TagSeverityMedium,
		}, tags)
		require.True(t, provider.getTagsCalled)
	})
}
