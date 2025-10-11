package accountprovider

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"time"

	"github.com/Amund211/flashlight/internal/constants"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
)

const getAccountMinOperationTime = 150 * time.Millisecond

type HttpClient interface {
	Do(req *http.Request) (*http.Response, error)
}

type RequestLimiter interface {
	Limit(ctx context.Context, minOperationTime time.Duration, operation func(ctx context.Context)) bool
}

type Mojang struct {
	httpClient HttpClient
	limiter    RequestLimiter
	nowFunc    func() time.Time
}

func NewMojang(httpClient HttpClient, nowFunc func() time.Time, afterFunc func(time.Duration) <-chan time.Time) *Mojang {
	// https://minecraft.wiki/w/Mojang_API
	baseLimiter := ratelimiting.NewWindowLimitRequestLimiter(600, 10*time.Minute, nowFunc, afterFunc)
	// Found by trial and error
	burstLimiter := ratelimiting.NewWindowLimitRequestLimiter(50, 8*time.Second, nowFunc, afterFunc)

	limiter := ratelimiting.NewComposedRequestLimiter(
		burstLimiter,
		baseLimiter,
	)

	return &Mojang{
		httpClient: httpClient,
		limiter:    limiter,
		nowFunc:    nowFunc,
	}
}

func (m *Mojang) GetAccountByUUID(ctx context.Context, uuid string) (domain.Account, error) {
	return m.getProfile(ctx, fmt.Sprintf("https://api.mojang.com/user/profile/%s", uuid))
}

func (m *Mojang) GetAccountByUsername(ctx context.Context, username string) (domain.Account, error) {
	return m.getProfile(ctx, fmt.Sprintf("https://api.mojang.com/users/profiles/minecraft/%s", username))
}

func (m *Mojang) getProfile(ctx context.Context, url string) (domain.Account, error) {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		err := fmt.Errorf("failed to create request: %w", err)
		reporting.Report(ctx, err)
		return domain.Account{}, err
	}

	req.Header.Set("User-Agent", constants.USER_AGENT)

	var resp *http.Response
	var data []byte
	ran := m.limiter.Limit(ctx, getAccountMinOperationTime, func(ctx context.Context) {
		resp, err = m.httpClient.Do(req)
		if err != nil {
			err := fmt.Errorf("failed to send request: %w", err)
			reporting.Report(ctx, err)
			return
		}

		defer resp.Body.Close()
		data, err = io.ReadAll(resp.Body)
		if err != nil {
			err := fmt.Errorf("failed to read response body: %w", err)
			reporting.Report(ctx, err)
			return
		}
	})
	if !ran {
		return domain.Account{}, fmt.Errorf("%w: too many requests to mojang API", domain.ErrTemporarilyUnavailable)
	}

	if err != nil {
		return domain.Account{}, err
	}

	identity, err := accountFromMojangResponse(resp.StatusCode, data, m.nowFunc())
	if err != nil {
		if errors.Is(err, domain.ErrUsernameNotFound) {
			// Pass through error but don't report
			return domain.Account{}, err
		}

		err := fmt.Errorf("failed to get identity from mojang response: %w", err)
		extra := map[string]string{
			"data":   string(data),
			"status": strconv.Itoa(resp.StatusCode),
		}
		for header, values := range resp.Header {
			switch len(values) {
			case 0:
				extra["header_"+header] = "<empty slice>"
			case 1:
				extra["header_"+header] = values[0]
			default:
				extra["header_"+header] = fmt.Sprintf("list: %v", values)
			}
		}
		reporting.Report(ctx, err, extra)
		return domain.Account{}, err
	}

	return identity, nil
}

type mojangResponse struct {
	UUID     string `json:"id"`
	Username string `json:"name"`
}

func accountFromMojangResponse(statusCode int, data []byte, queriedAt time.Time) (domain.Account, error) {
	switch statusCode {
	case http.StatusTooManyRequests,
		http.StatusServiceUnavailable,
		http.StatusGatewayTimeout:
		return domain.Account{}, fmt.Errorf("%w: mojang API returned status code %d", domain.ErrTemporarilyUnavailable, statusCode)
	}

	switch statusCode {
	case http.StatusNotFound,
		http.StatusNoContent:
		return domain.Account{}, domain.ErrUsernameNotFound
	}

	var response mojangResponse
	if err := json.Unmarshal(data, &response); err != nil {
		return domain.Account{}, fmt.Errorf("failed to parse mojang response: %w", err)
	}

	uuid, err := strutils.NormalizeUUID(response.UUID)
	if err != nil {
		return domain.Account{}, fmt.Errorf("failed to normalize UUID from mojang: %w", err)
	}

	return domain.Account{
		Username:  response.Username,
		UUID:      uuid,
		QueriedAt: queriedAt,
	}, nil
}
