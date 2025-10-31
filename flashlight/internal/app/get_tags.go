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
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
)

type GetTags func(ctx context.Context, uuid string, apiKey *string) (domain.Tags, error)

type getTagsMetricsCollection struct {
	returnCount metric.Int64Counter
}

func setupGetTagsMetrics(meter metric.Meter) (getTagsMetricsCollection, error) {
	returnCount, err := meter.Int64Counter("app/get_tags/return_count")
	if err != nil {
		return getTagsMetricsCollection{}, fmt.Errorf("failed to create return count metric: %w", err)
	}

	return getTagsMetricsCollection{
		returnCount: returnCount,
	}, nil
}

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
) (GetTags, error) {
	const name = "flashlight/app/get_tags"

	meter := otel.Meter(name)

	metrics, err := setupGetTagsMetrics(meter)
	if err != nil {
		return nil, fmt.Errorf("failed to set up metrics: %w", err)
	}

	getTagsWithoutCache := buildGetTagsWithoutCache(provider)

	type trackingInfo struct {
		cached       bool
		success      bool
		invalidInput bool
	}

	track := func(ctx context.Context, info trackingInfo) {
		metrics.returnCount.Add(
			ctx,
			1,
			metric.WithAttributes(
				attribute.Bool("cached", info.cached),
				attribute.Bool("success", info.success),
				attribute.Bool("invalid_input", info.invalidInput),
			),
		)
	}

	return func(ctx context.Context, uuid string, apiKey *string) (domain.Tags, error) {
		if !strutils.UUIDIsNormalized(uuid) {
			err := fmt.Errorf("UUID is not normalized")
			reporting.Report(ctx, err)
			track(ctx, trackingInfo{success: false, invalidInput: true})
			return domain.Tags{}, err
		}

		apiKeyHash := "missing"
		if apiKey != nil {
			apiKeyHash = fmt.Sprintf("%x", sha256.Sum256([]byte(*apiKey)))
		}

		key := fmt.Sprintf("uuid:%s|apiKeyHash:%s", uuid, apiKeyHash)

		tags, created, err := cache.GetOrCreate(ctx, tagsByUUIDCache, key, func() (domain.Tags, error) {
			return getTagsWithoutCache(ctx, uuid, apiKey)
		})
		if err != nil {
			// NOTE: GetOrCreate only returns an error if create() fails.
			// getTagsWithoutCache handles its own error reporting
			track(ctx, trackingInfo{success: false})
			return domain.Tags{}, fmt.Errorf("failed to cache.GetOrCreate tags for uuid: %w", err)
		}

		track(ctx, trackingInfo{success: true, cached: !created})
		return tags, nil
	}, nil
}
