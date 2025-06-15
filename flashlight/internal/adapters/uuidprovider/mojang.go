package uuidprovider

import (
	"context"
	"encoding/json"
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

func (m mojangUUIDProvider) GetUUID(ctx context.Context, username string) (string, error) {
	url := fmt.Sprintf("https://api.mojang.com/users/profiles/minecraft/%s", username)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		err := fmt.Errorf("failed to create request: %w", err)
		reporting.Report(ctx, err)
		return "", err
	}

	req.Header.Set("User-Agent", constants.USER_AGENT)

	resp, err := m.httpClient.Do(req)
	if err != nil {
		err := fmt.Errorf("failed to send request: %w", err)
		reporting.Report(ctx, err)
		return "", err
	}

	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		err := fmt.Errorf("failed to read response body: %w", err)
		reporting.Report(ctx, err)
		return "", err
	}

	uuid, err := uuidFromMojangResponse(resp.StatusCode, data)
	if err != nil {
		err := fmt.Errorf("failed to get uuid from mojang response: %w", err)
		reporting.Report(ctx, err, map[string]string{
			"data":   string(data),
			"status": strconv.Itoa(resp.StatusCode),
		})
		return "", err
	}

	return uuid, nil
}

type mojangResponse struct {
	UUID string `json:"id"`
}

func uuidFromMojangResponse(statusCode int, data []byte) (string, error) {
	switch statusCode {
	case http.StatusTooManyRequests,
		http.StatusServiceUnavailable,
		http.StatusGatewayTimeout:
		return "", fmt.Errorf("%w: mojang API returned status code %d", domain.ErrTemporarilyUnavailable, statusCode)
	}

	switch statusCode {
	case http.StatusNotFound,
		http.StatusNoContent:
		return "", domain.ErrUsernameNotFound
	}

	var response mojangResponse
	if err := json.Unmarshal(data, &response); err != nil {
		return "", fmt.Errorf("failed to parse mojang response: %w", err)
	}

	uuid, err := strutils.NormalizeUUID(response.UUID)
	if err != nil {
		return "", fmt.Errorf("failed to normalize UUID from mojang: %w", err)
	}

	return uuid, nil
}

func NewMojangUUIDProvider(httpClient HttpClient) UUIDProvider {
	return mojangUUIDProvider{
		httpClient: httpClient,
	}
}
