package uuidprovider

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strconv"

	"github.com/Amund211/flashlight/internal/constants"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
)

type HttpClient interface {
	Do(req *http.Request) (*http.Response, error)
}

type mojangUUIDProvider struct {
	httpClient HttpClient
}

func (m mojangUUIDProvider) GetUUID(ctx context.Context, username string) (Identity, error) {
	url := fmt.Sprintf("https://api.mojang.com/users/profiles/minecraft/%s", username)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		err := fmt.Errorf("failed to create request: %w", err)
		reporting.Report(ctx, err)
		return Identity{}, err
	}

	req.Header.Set("User-Agent", constants.USER_AGENT)

	resp, err := m.httpClient.Do(req)
	if err != nil {
		err := fmt.Errorf("failed to send request: %w", err)
		reporting.Report(ctx, err)
		return Identity{}, err
	}

	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		err := fmt.Errorf("failed to read response body: %w", err)
		reporting.Report(ctx, err)
		return Identity{}, err
	}

	identity, err := identityFromMojangResponse(resp.StatusCode, data)
	if err != nil {
		if errors.Is(err, domain.ErrUsernameNotFound) {
			// Pass through error but don't report
			return Identity{}, err
		}

		err := fmt.Errorf("failed to get identity from mojang response: %w", err)
		reporting.Report(ctx, err, map[string]string{
			"data":   string(data),
			"status": strconv.Itoa(resp.StatusCode),
		})
		return Identity{}, err
	}

	return identity, nil
}

type mojangResponse struct {
	UUID     string `json:"id"`
	Username string `json:"name"`
}

func identityFromMojangResponse(statusCode int, data []byte) (Identity, error) {
	switch statusCode {
	case http.StatusTooManyRequests,
		http.StatusServiceUnavailable,
		http.StatusGatewayTimeout:
		return Identity{}, fmt.Errorf("%w: mojang API returned status code %d", domain.ErrTemporarilyUnavailable, statusCode)
	}

	switch statusCode {
	case http.StatusNotFound,
		http.StatusNoContent:
		return Identity{}, domain.ErrUsernameNotFound
	}

	var response mojangResponse
	if err := json.Unmarshal(data, &response); err != nil {
		return Identity{}, fmt.Errorf("failed to parse mojang response: %w", err)
	}

	uuid, err := strutils.NormalizeUUID(response.UUID)
	if err != nil {
		return Identity{}, fmt.Errorf("failed to normalize UUID from mojang: %w", err)
	}

	return Identity{
		Username: response.Username,
		UUID:     uuid,
	}, nil
}

func NewMojangUUIDProvider(httpClient HttpClient) UUIDProvider {
	return mojangUUIDProvider{
		httpClient: httpClient,
	}
}
