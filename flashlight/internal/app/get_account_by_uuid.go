package app

import (
	"context"
	"errors"
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

type GetAccountByUUID func(ctx context.Context, uuid string) (domain.Account, error)

type getAccountByUUIDMetricsCollection struct {
	requestCount metric.Int64Counter
	returnCount  metric.Int64Counter
}

func setupGetAccountByUUIDMetrics(meter metric.Meter) (getAccountByUUIDMetricsCollection, error) {
	requestCount, err := meter.Int64Counter("app/get_account_by_uuid/request_count")
	if err != nil {
		return getAccountByUUIDMetricsCollection{}, fmt.Errorf("failed to create request count metric: %w", err)
	}

	returnCount, err := meter.Int64Counter("app/get_account_by_uuid/return_count")
	if err != nil {
		return getAccountByUUIDMetricsCollection{}, fmt.Errorf("failed to create return count metric: %w", err)
	}

	return getAccountByUUIDMetricsCollection{
		requestCount: requestCount,
		returnCount:  returnCount,
	}, nil
}

type accountProviderByUUID interface {
	GetAccountByUUID(ctx context.Context, uuid string) (domain.Account, error)
}

type accountRepositoryByUUID interface {
	StoreAccount(ctx context.Context, account domain.Account) error
	GetAccountByUUID(ctx context.Context, uuid string) (domain.Account, error)
}

func buildGetAccountByUUIDWithoutCache(
	provider accountProviderByUUID,
	repo accountRepositoryByUUID,
	nowFunc func() time.Time,
	metrics getAccountByUUIDMetricsCollection,
) func(ctx context.Context, uuid string) (domain.Account, error) {
	type trackingInfo struct {
		source         string
		found          bool
		recovered      bool
		providerFailed bool
		failed         bool
	}

	track := func(ctx context.Context, info trackingInfo) {
		if info.source == "" {
			info.source = "unknown"
		}
		metrics.requestCount.Add(
			ctx,
			1,
			metric.WithAttributes(
				attribute.String("source", info.source),
				attribute.Bool("found", info.found),
				attribute.Bool("recovered", info.recovered),
				attribute.Bool("provider_failed", info.providerFailed),
				attribute.Bool("failed", info.failed),
			),
		)
	}

	return func(ctx context.Context, uuid string) (domain.Account, error) {
		getCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
		defer cancel()
		providerAccount, err := provider.GetAccountByUUID(getCtx, uuid)
		if errors.Is(err, domain.ErrUsernameNotFound) {
			track(ctx, trackingInfo{source: "provider", found: false})
			return domain.Account{}, err
		} else if err != nil {
			// NOTE: accountProvider implementations handle their own error reporting

			// Try to fall back to the repository result, if available
			if repoAccount, err := repo.GetAccountByUUID(ctx, uuid); err == nil {
				// time.Since(repoAccount.QueriedAt) implemented using nowFunc()
				repoAccountAge := nowFunc().Sub(repoAccount.QueriedAt)
				// Very lenient fallback in case the provider fails
				// Getting the incorrect name is not critical
				if repoAccountAge < 30*24*time.Hour {
					// We have a valid, recent-ish account from the repository, return it
					track(ctx, trackingInfo{
						source:         "repository",
						providerFailed: true,
						recovered:      true,
						found:          true,
					})
					return repoAccount, nil
				}

			}
			track(ctx, trackingInfo{providerFailed: true, failed: true})
			return domain.Account{}, fmt.Errorf("could not get account for uuid: %w", err)
		}

		err = repo.StoreAccount(ctx, domain.Account{
			UUID:      providerAccount.UUID,
			Username:  providerAccount.Username,
			QueriedAt: providerAccount.QueriedAt,
		})
		if err != nil {
			// NOTE: This error is not critical, we can still return the account
		}

		track(ctx, trackingInfo{source: "provider", found: true})
		return providerAccount, nil
	}
}

func BuildGetAccountByUUIDWithCache(
	accountByUUIDCache cache.Cache[domain.Account],
	provider accountProviderByUUID,
	repo accountRepositoryByUUID,
	nowFunc func() time.Time,
) (GetAccountByUUID, error) {
	const name = "flashlight/app/get_account_by_uuid_with_cache"

	meter := otel.Meter(name)

	metrics, err := setupGetAccountByUUIDMetrics(meter)
	if err != nil {
		return nil, fmt.Errorf("failed to set up metrics: %w", err)
	}

	getAccountByUUIDWithoutCache := buildGetAccountByUUIDWithoutCache(provider, repo, nowFunc, metrics)

	type trackingInfo struct {
		found        bool
		cached       bool
		success      bool
		invalidInput bool
	}

	track := func(ctx context.Context, info trackingInfo) {
		metrics.returnCount.Add(
			ctx,
			1,
			metric.WithAttributes(
				attribute.Bool("found", info.found),
				attribute.Bool("cached", info.cached),
				attribute.Bool("success", info.success),
				attribute.Bool("invalid_input", info.invalidInput),
			),
		)
	}

	return func(ctx context.Context, uuid string) (domain.Account, error) {
		if !strutils.UUIDIsNormalized(uuid) {
			err := fmt.Errorf("UUID is not normalized")
			reporting.Report(ctx, err)
			track(ctx, trackingInfo{success: false, invalidInput: true})
			return domain.Account{}, err
		}

		account, created, err := cache.GetOrCreate(ctx, accountByUUIDCache, uuid, func() (domain.Account, error) {
			return getAccountByUUIDWithoutCache(ctx, uuid)
		})
		if errors.Is(err, domain.ErrUsernameNotFound) {
			track(ctx, trackingInfo{success: true, found: false})
			return domain.Account{}, err
		} else if err != nil {
			// NOTE: GetOrCreate only returns an error if create() fails.
			// getAccountByUUIDWithoutCache handles its own error reporting
			track(ctx, trackingInfo{success: false})
			return domain.Account{}, fmt.Errorf("failed to cache.GetOrCreate account for uuid: %w", err)
		}

		track(ctx, trackingInfo{success: true, found: true, cached: !created})
		return account, nil
	}, nil
}
