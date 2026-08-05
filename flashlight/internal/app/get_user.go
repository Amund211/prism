package app

import (
	"context"
	"errors"
	"fmt"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"

	"github.com/Amund211/flashlight/internal/adapters/cache"
	"github.com/Amund211/flashlight/internal/domain"
)

// GetUser resolves an overlay user by their user ID. Returns
// domain.ErrUserNotFound when we have never seen the user.
type GetUser func(ctx context.Context, userID string) (domain.User, error)

type getUserRepository interface {
	GetUser(ctx context.Context, userID string) (domain.User, error)
}

type getUserMetricsCollection struct {
	returnCount metric.Int64Counter
}

func setupGetUserMetrics(meter metric.Meter) (getUserMetricsCollection, error) {
	returnCount, err := meter.Int64Counter("app/get_user/return_count")
	if err != nil {
		return getUserMetricsCollection{}, fmt.Errorf("failed to create return count metric: %w", err)
	}

	return getUserMetricsCollection{
		returnCount: returnCount,
	}, nil
}

// BuildGetUserWithCache returns a GetUser that caches found users. Not found
// results and lookup failures are not cached.
func BuildGetUserWithCache(
	userCache cache.Cache[domain.User],
	repo getUserRepository,
) (GetUser, error) {
	const name = "flashlight/app/get_user_with_cache"

	meter := otel.Meter(name)

	metrics, err := setupGetUserMetrics(meter)
	if err != nil {
		return nil, fmt.Errorf("failed to set up metrics: %w", err)
	}

	type trackingInfo struct {
		success bool
		found   bool
		cached  bool
	}

	track := func(ctx context.Context, info trackingInfo) {
		metrics.returnCount.Add(
			ctx,
			1,
			metric.WithAttributes(
				attribute.Bool("success", info.success),
				attribute.Bool("found", info.found),
				attribute.Bool("cached", info.cached),
			),
		)
	}

	return func(ctx context.Context, userID string) (domain.User, error) {
		user, created, err := cache.GetOrCreate(ctx, userCache, userID, func() (domain.User, error) {
			return repo.GetUser(ctx, userID)
		})
		if errors.Is(err, domain.ErrUserNotFound) {
			track(ctx, trackingInfo{success: true, found: false})
			return domain.User{}, err
		} else if err != nil {
			// NOTE: The error is either create()'s — the user repository
			// handles its own error reporting — or GetOrCreate giving up on a
			// done context or a contended entry, which it logs itself.
			track(ctx, trackingInfo{success: false})
			return domain.User{}, fmt.Errorf("failed to cache.GetOrCreate user: %w", err)
		}

		track(ctx, trackingInfo{success: true, found: true, cached: !created})
		return user, nil
	}, nil
}
