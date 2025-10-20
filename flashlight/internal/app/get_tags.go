package app

import (
	"context"
	"crypto/sha256"
	"fmt"
	"time"

	"github.com/Amund211/flashlight/internal/adapters/cache"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
)

type GetTags func(ctx context.Context, uuid string, apiKey *string) (domain.Tags, error)

type tagProvider interface {
	GetTags(ctx context.Context, uuid string, apiKey *string) (domain.Tags, error)
}

func buildGetTagsWithoutCache(
	provider tagProvider,
) func(ctx context.Context, uuid string, apiKey *string) (domain.Tags, error) {
	return func(ctx context.Context, uuid string, apiKey *string) (domain.Tags, error) {
		ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
		defer cancel()
		tags, err := provider.GetTags(ctx, uuid, apiKey)
		if err != nil {
			// NOTE: tagProvider implementations handle their own error reporting
			return domain.Tags{}, fmt.Errorf("could not get tags for uuid: %w", err)
		}

		return tags, nil
	}
}

func BuildGetTagsWithCache(
	tagsByUUIDCache cache.Cache[domain.Tags],
	provider tagProvider,
) GetTags {
	getTagsWithoutCache := buildGetTagsWithoutCache(provider)

	return func(ctx context.Context, uuid string, apiKey *string) (domain.Tags, error) {
		if !strutils.UUIDIsNormalized(uuid) {
			err := fmt.Errorf("UUID is not normalized")
			reporting.Report(ctx, err)
			return domain.Tags{}, err
		}

		apiKeyHash := "missing"
		if apiKey != nil {
			apiKeyHash = fmt.Sprintf("%x", sha256.Sum256([]byte(*apiKey)))
		}

		key := fmt.Sprintf("uuid:%s|apiKeyHash:%s", uuid, apiKeyHash)

		tags, err := cache.GetOrCreate(ctx, tagsByUUIDCache, key, func() (domain.Tags, error) {
			return getTagsWithoutCache(ctx, uuid, apiKey)
		})
		if err != nil {
			// NOTE: GetOrCreate only returns an error if create() fails.
			// getTagsWithoutCache handles its own error reporting
			return domain.Tags{}, fmt.Errorf("failed to cache.GetOrCreate tags for uuid: %w", err)
		}

		return tags, nil
	}
}
