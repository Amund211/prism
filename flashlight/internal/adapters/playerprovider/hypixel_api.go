package playerprovider

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/Amund211/flashlight/internal/config"
	"github.com/Amund211/flashlight/internal/constants"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
)

const getPlayerDataMinOperationTime = 100 * time.Millisecond

type HttpClient interface {
	Do(req *http.Request) (*http.Response, error)
}

type RequestLimiter interface {
	Limit(ctx context.Context, minOperationTime time.Duration, operation func()) bool
}

type HypixelAPI interface {
	GetPlayerData(ctx context.Context, uuid string) ([]byte, int, time.Time, error)
}

type mockedHypixelAPI struct{}

func (hypixelAPI *mockedHypixelAPI) GetPlayerData(ctx context.Context, uuid string) ([]byte, int, time.Time, error) {
	return []byte(fmt.Sprintf(`{"success":true,"player":{"uuid":"%s"}}`, uuid)), 200, time.Now(), nil
}

type hypixelAPIImpl struct {
	httpClient HttpClient
	limiter    RequestLimiter
	nowFunc    func() time.Time
	apiKey     string
}

func (hypixelAPI hypixelAPIImpl) GetPlayerData(ctx context.Context, uuid string) ([]byte, int, time.Time, error) {
	logger := logging.FromContext(ctx)
	url := fmt.Sprintf("https://api.hypixel.net/player?uuid=%s", uuid)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		err := fmt.Errorf("failed to create request: %w", err)
		logger.Error(err.Error())
		reporting.Report(ctx, err)
		return []byte{}, -1, time.Time{}, err
	}

	req.Header.Set("User-Agent", constants.USER_AGENT)
	req.Header.Set("API-Key", hypixelAPI.apiKey)

	var resp *http.Response
	var data []byte
	var queriedAt time.Time
	ran := hypixelAPI.limiter.Limit(ctx, getPlayerDataMinOperationTime, func() {
		resp, err = hypixelAPI.httpClient.Do(req)
		if err != nil {
			err := fmt.Errorf("failed to send request: %w", err)
			logger.Error(err.Error())
			reporting.Report(ctx, err)
			return
		}

		queriedAt = hypixelAPI.nowFunc()

		defer resp.Body.Close()
		data, err = io.ReadAll(resp.Body)
		if err != nil {
			err := fmt.Errorf("failed to read response body: %w", err)
			logger.Error(err.Error())
			reporting.Report(ctx, err)
			return
		}
	})
	if !ran {
		return []byte{}, -1, time.Time{}, fmt.Errorf("%w: too many requests to Hypixel API", domain.ErrTemporarilyUnavailable)
	}

	if err != nil {
		return []byte{}, -1, time.Time{}, err
	}

	return data, resp.StatusCode, queriedAt, nil
}

func NewHypixelAPI(
	httpClient HttpClient,
	nowFunc func() time.Time,
	afterFunc func(d time.Duration) <-chan time.Time,
	apiKey string,
) HypixelAPI {
	limiter := ratelimiting.NewWindowLimitRequestLimiter(600, 5*time.Minute, nowFunc, afterFunc)
	return hypixelAPIImpl{
		httpClient: httpClient,
		limiter:    limiter,
		nowFunc:    nowFunc,
		apiKey:     apiKey,
	}
}

func NewHypixelAPIOrMock(
	config config.Config,
	httpClient HttpClient,
	nowFunc func() time.Time,
	afterFunc func(d time.Duration) <-chan time.Time,
) (HypixelAPI, error) {
	if config.HypixelAPIKey() != "" {
		return NewHypixelAPI(httpClient, nowFunc, afterFunc, config.HypixelAPIKey()), nil
	}
	if config.IsDevelopment() {
		return &mockedHypixelAPI{}, nil
	}
	return nil, fmt.Errorf("Missing Hypixel API key in non-development environment")
}
