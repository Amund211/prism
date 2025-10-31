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
)

type GetAccountByUUID func(ctx context.Context, uuid string) (domain.Account, error)

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
) func(ctx context.Context, uuid string) (domain.Account, error) {
	return func(ctx context.Context, uuid string) (domain.Account, error) {
		if !strutils.UUIDIsNormalized(uuid) {
			err := fmt.Errorf("UUID is not normalized")
			reporting.Report(ctx, err)
			return domain.Account{}, err
		}

		getCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
		defer cancel()
		providerAccount, err := provider.GetAccountByUUID(getCtx, uuid)
		if errors.Is(err, domain.ErrUsernameNotFound) {
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
					return repoAccount, nil
				}

			}
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

		return providerAccount, nil
	}
}

func BuildGetAccountByUUIDWithCache(
	accountByUUIDCache cache.Cache[domain.Account],
	provider accountProviderByUUID,
	repo accountRepositoryByUUID,
	nowFunc func() time.Time,
) GetAccountByUUID {
	getAccountByUUIDWithoutCache := buildGetAccountByUUIDWithoutCache(provider, repo, nowFunc)

	return func(ctx context.Context, uuid string) (domain.Account, error) {
		account, _, err := cache.GetOrCreate(ctx, accountByUUIDCache, uuid, func() (domain.Account, error) {
			return getAccountByUUIDWithoutCache(ctx, uuid)
		})
		if err != nil {
			// NOTE: GetOrCreate only returns an error if create() fails.
			// getAccountByUUIDWithoutCache handles its own error reporting
			return domain.Account{}, fmt.Errorf("failed to cache.GetOrCreate account for uuid: %w", err)
		}

		return account, nil
	}
}
