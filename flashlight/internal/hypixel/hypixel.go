package hypixel

import (
	"context"
	"fmt"
	"io"
	"net/http"

	"github.com/Amund211/flashlight/internal/constants"
	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/Amund211/flashlight/internal/logging"
)

type HttpClient interface {
	Do(req *http.Request) (*http.Response, error)
}

type HypixelAPI interface {
	GetPlayerData(ctx context.Context, uuid string) ([]byte, int, error)
}

type hypixelAPIImpl struct {
	httpClient HttpClient
	apiKey     string
}

func (hypixelAPI hypixelAPIImpl) GetPlayerData(ctx context.Context, uuid string) ([]byte, int, error) {
	logger := logging.FromContext(ctx)
	url := fmt.Sprintf("https://api.hypixel.net/player?uuid=%s", uuid)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		logger.Error("Failed to create request", "error", err)
		return []byte{}, -1, fmt.Errorf("%w: %w", e.APIServerError, err)
	}

	req.Header.Set("User-Agent", constants.USER_AGENT)
	req.Header.Set("API-Key", hypixelAPI.apiKey)

	resp, err := hypixelAPI.httpClient.Do(req)
	if err != nil {
		logger.Error("Failed to send request", "error", err)
		return []byte{}, -1, fmt.Errorf("%w: %w", e.APIServerError, err)
	}

	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		logger.Error("Failed to read response body", "error", err)
		return []byte{}, -1, fmt.Errorf("%w: %w", e.APIServerError, err)
	}

	return data, resp.StatusCode, nil
}

func NewHypixelAPI(httpClient HttpClient, apiKey string) HypixelAPI {
	return hypixelAPIImpl{
		httpClient: httpClient,
		apiKey:     apiKey,
	}
}
