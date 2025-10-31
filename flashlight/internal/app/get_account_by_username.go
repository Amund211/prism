package app

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	"github.com/Amund211/flashlight/internal/adapters/cache"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
)

type GetAccountByUsername func(ctx context.Context, username string) (domain.Account, error)

type getAccountByUsernameMetricsCollection struct {
	requestCount metric.Int64Counter
	returnCount  metric.Int64Counter
}

func setupGetAccountByUsernameMetrics(meter metric.Meter) (getAccountByUsernameMetricsCollection, error) {
	requestCount, err := meter.Int64Counter("app/get_account_by_username/request_count")
	if err != nil {
		return getAccountByUsernameMetricsCollection{}, fmt.Errorf("failed to create request count metric: %w", err)
	}

	returnCount, err := meter.Int64Counter("app/get_account_by_username/return_count")
	if err != nil {
		return getAccountByUsernameMetricsCollection{}, fmt.Errorf("failed to create return count metric: %w", err)
	}

	return getAccountByUsernameMetricsCollection{
		requestCount: requestCount,
		returnCount:  returnCount,
	}, nil
}

type accountProviderByUsername interface {
	GetAccountByUsername(ctx context.Context, username string) (domain.Account, error)
}

type accountRepositoryByUsername interface {
	StoreAccount(ctx context.Context, account domain.Account) error
	RemoveUsername(ctx context.Context, username string) error
	GetAccountByUsername(ctx context.Context, username string) (domain.Account, error)
}

func buildGetAccountByUsernameWithoutCache(
	provider accountProviderByUsername,
	repo accountRepositoryByUsername,
	nowFunc func() time.Time,
	metrics getAccountByUsernameMetricsCollection,
) func(ctx context.Context, username string) (domain.Account, error) {
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

	return func(ctx context.Context, username string) (domain.Account, error) {
		repoAccount, repoGetErr := repo.GetAccountByUsername(ctx, username)
		if errors.Is(repoGetErr, domain.ErrUsernameNotFound) {
			// No entry in the repo - try to query the provider
		} else if repoGetErr != nil {
			// Failed to get account from repository - can still try to query the provider
			// NOTE: accountRepository implementations handle their own error reporting
		} else {
			// time.Since(repoAccount.QueriedAt) implemented using nowFunc()
			repoAccountAge := nowFunc().Sub(repoAccount.QueriedAt)
			if repoAccountAge < 10*24*time.Hour {
				if !strutils.UUIDIsNormalized(repoAccount.UUID) {
					err := fmt.Errorf("UUID from repo is not normalized")
					reporting.Report(ctx, err, map[string]string{
						"uuid": repoAccount.UUID,
					})
					// We can still try to query the provider
				} else {
					// We have a valid, recent account from the repository, return it
					track(ctx, trackingInfo{source: "repository", found: true})
					return repoAccount, nil
				}
			}
		}

		getCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
		defer cancel()
		providerAccount, err := provider.GetAccountByUsername(getCtx, username)
		if errors.Is(err, domain.ErrUsernameNotFound) {
			removeUsernameErr := repo.RemoveUsername(ctx, username)
			if removeUsernameErr != nil {
				// NOTE: accountRepository implementations handle their own error reporting
				// Still fall through to return the ErrUsernameNotFound
			}

			// Pass through ErrUsernameNotFound to the caller
			track(ctx, trackingInfo{source: "provider", found: false})
			return domain.Account{}, err
		} else if err != nil {
			// NOTE: accountProvider implementations handle their own error reporting

			// Try to fall back to the repository result, if available
			if repoGetErr == nil {
				// time.Since(repoAccount.QueriedAt) implemented using nowFunc()
				repoAccountAge := nowFunc().Sub(repoAccount.QueriedAt)
				// 30 day name change interval + 7 days grace period of reclaiming your name
				if repoAccountAge < 37*24*time.Hour {
					if !strutils.UUIDIsNormalized(repoAccount.UUID) {
						err := fmt.Errorf("UUID from repo is not normalized")
						reporting.Report(ctx, err, map[string]string{
							"uuid": repoAccount.UUID,
						})
					} else {
						// We have a valid, recent-ish account from the repository, return it
						track(ctx, trackingInfo{
							source:         "repository",
							found:          true,
							providerFailed: true,
							recovered:      true,
						})
						return repoAccount, nil
					}
				}
			}

			track(ctx, trackingInfo{providerFailed: true, failed: true})
			return domain.Account{}, fmt.Errorf("could not get account for username: %w", err)
		}

		if !strutils.UUIDIsNormalized(providerAccount.UUID) {
			err := fmt.Errorf("UUID is not normalized")
			reporting.Report(ctx, err, map[string]string{
				"uuid": providerAccount.UUID,
			})
			track(ctx, trackingInfo{providerFailed: true, failed: true})
			return domain.Account{}, err
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

func BuildGetAccountByUsernameWithCache(
	accountByUsernameCache cache.Cache[domain.Account],
	provider accountProviderByUsername,
	repo accountRepositoryByUsername,
	nowFunc func() time.Time,
) (GetAccountByUsername, error) {
	const name = "flashlight/app/get_account_by_username_with_cache"

	meter := otel.Meter(name)

	metrics, err := setupGetAccountByUsernameMetrics(meter)
	if err != nil {
		return nil, fmt.Errorf("failed to set up metrics: %w", err)
	}

	getAccountByUsernameWithoutCache := buildGetAccountByUsernameWithoutCache(provider, repo, nowFunc, metrics)

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

	return func(ctx context.Context, username string) (domain.Account, error) {
		usernameLength := len(username)
		if usernameLength == 0 || usernameLength > 100 {
			err := fmt.Errorf("invalid username length")
			reporting.Report(ctx, err, map[string]string{
				"username": username,
				"length":   strconv.Itoa(usernameLength),
			})
			track(ctx, trackingInfo{invalidInput: true})
			return domain.Account{}, err
		}

		// No two accounts can have the same username with case-insensitive comparison
		cacheKey := strings.ToLower(username)

		account, created, err := cache.GetOrCreate(ctx, accountByUsernameCache, cacheKey, func() (domain.Account, error) {
			return getAccountByUsernameWithoutCache(ctx, username)
		})
		if errors.Is(err, domain.ErrUsernameNotFound) {
			track(ctx, trackingInfo{success: true, found: false})
			return domain.Account{}, err
		} else if err != nil {
			// NOTE: GetOrCreate only returns an error if create() fails.
			// getAccountByUsernameWithoutCache handles its own error reporting
			track(ctx, trackingInfo{success: false})
			return domain.Account{}, fmt.Errorf("failed to cache.GetOrCreate account for username: %w", err)
		}

		track(ctx, trackingInfo{success: true, found: true, cached: !created})
		return account, nil
	}, nil
}
