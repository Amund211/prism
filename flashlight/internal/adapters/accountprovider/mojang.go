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
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
)

type HttpClient interface {
	Do(req *http.Request) (*http.Response, error)
}

type Mojang struct {
	httpClient HttpClient
	nowFunc    func() time.Time
}

func NewMojang(httpClient HttpClient, nowFunc func() time.Time) *Mojang {
	return &Mojang{
		httpClient: httpClient,
		nowFunc:    nowFunc,
	}
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

	resp, err := m.httpClient.Do(req)
	if err != nil {
		err := fmt.Errorf("failed to send request: %w", err)
		reporting.Report(ctx, err)
		return domain.Account{}, err
	}

	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		err := fmt.Errorf("failed to read response body: %w", err)
		reporting.Report(ctx, err)
		return domain.Account{}, err
	}

	identity, err := accountFromMojangResponse(resp.StatusCode, data, m.nowFunc())
	if err != nil {
		if errors.Is(err, domain.ErrUsernameNotFound) {
			// Pass through error but don't report
			return domain.Account{}, err
		}

		err := fmt.Errorf("failed to get identity from mojang response: %w", err)
		reporting.Report(ctx, err, map[string]string{
			"data":   string(data),
			"status": strconv.Itoa(resp.StatusCode),
		})
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
