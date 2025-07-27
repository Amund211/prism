package app

import (
	"context"
	"fmt"
	"strconv"

	"github.com/Amund211/flashlight/internal/adapters/cache"
	"github.com/Amund211/flashlight/internal/adapters/uuidprovider"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
)

type GetUUID func(ctx context.Context, username string) (string, error)

func getUUIDWithoutCache(ctx context.Context, provider uuidprovider.UUIDProvider, username string) (string, error) {
	identity, err := provider.GetUUID(ctx, username)
	if err != nil {
		// NOTE: UUIDProvider implementations handle their own error reporting
		return "", fmt.Errorf("could not get uuid for username: %w", err)
	}

	if !strutils.UUIDIsNormalized(identity.UUID) {
		err := fmt.Errorf("UUID is not normalized")
		reporting.Report(ctx, err, map[string]string{
			"uuid": identity.UUID,
		})
		return "", err
	}

	return identity.UUID, nil
}

func BuildGetUUIDWithCache(uuidCache cache.Cache[string], provider uuidprovider.UUIDProvider) GetUUID {
	return func(ctx context.Context, username string) (string, error) {
		usernameLength := len(username)
		if usernameLength == 0 || usernameLength > 100 {
			err := fmt.Errorf("invalid username length")
			reporting.Report(ctx, err, map[string]string{
				"username": username,
				"length":   strconv.Itoa(usernameLength),
			})
			return "", err
		}

		uuid, err := cache.GetOrCreate(ctx, uuidCache, username, func() (string, error) {
			return getUUIDWithoutCache(ctx, provider, username)
		})
		if err != nil {
			// NOTE: GetOrCreate only returns an error if create() fails.
			// getUUIDWithoutCache handles its own error reporting
			return "", fmt.Errorf("failed to cache.GetOrCreate uuid for username: %w", err)
		}

		return uuid, nil
	}
}
