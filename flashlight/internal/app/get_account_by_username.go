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
)

type GetAccountByUsername func(ctx context.Context, username string) (domain.Account, error)

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
) func(ctx context.Context, username string) (domain.Account, error) {
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
						return repoAccount, nil
					}
				}

			}
			return domain.Account{}, fmt.Errorf("could not get account for username: %w", err)
		}

		if !strutils.UUIDIsNormalized(providerAccount.UUID) {
			err := fmt.Errorf("UUID is not normalized")
			reporting.Report(ctx, err, map[string]string{
				"uuid": providerAccount.UUID,
			})
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

		return providerAccount, nil
	}
}

func BuildGetAccountByUsernameWithCache(
	accountByUsernameCache cache.Cache[domain.Account],
	provider accountProviderByUsername,
	repo accountRepositoryByUsername,
	nowFunc func() time.Time,
) GetAccountByUsername {
	getAccountByUsernameWithoutCache := buildGetAccountByUsernameWithoutCache(provider, repo, nowFunc)

	return func(ctx context.Context, username string) (domain.Account, error) {
		usernameLength := len(username)
		if usernameLength == 0 || usernameLength > 100 {
			err := fmt.Errorf("invalid username length")
			reporting.Report(ctx, err, map[string]string{
				"username": username,
				"length":   strconv.Itoa(usernameLength),
			})
			return domain.Account{}, err
		}

		// No two accounts can have the same username with case-insensitive comparison
		cacheKey := strings.ToLower(username)

		account, err := cache.GetOrCreate(ctx, accountByUsernameCache, cacheKey, func() (domain.Account, error) {
			return getAccountByUsernameWithoutCache(ctx, username)
		})
		if err != nil {
			// NOTE: GetOrCreate only returns an error if create() fails.
			// getAccountByUsernameWithoutCache handles its own error reporting
			return domain.Account{}, fmt.Errorf("failed to cache.GetOrCreate account for username: %w", err)
		}

		return account, nil
	}
}
