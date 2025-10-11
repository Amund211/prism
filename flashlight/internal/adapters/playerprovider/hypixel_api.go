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
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/trace"
)

const getPlayerDataMinOperationTime = 100 * time.Millisecond

type HttpClient interface {
	Do(req *http.Request) (*http.Response, error)
}

type RequestLimiter interface {
	Limit(ctx context.Context, minOperationTime time.Duration, operation func(ctx context.Context)) bool
}

type HypixelAPI interface {
	GetPlayerData(ctx context.Context, uuid string) ([]byte, int, time.Time, error)
}

type hypixelAPIMetricsCollection struct {
	requestCount metric.Int64Counter
}

func setupHypixelAPIMetrics(meter metric.Meter) (hypixelAPIMetricsCollection, error) {
	requestCount, err := meter.Int64Counter("playerprovider/hypixel_api/request_count")
	if err != nil {
		return hypixelAPIMetricsCollection{}, fmt.Errorf("failed to create metric: %w", err)
	}

	return hypixelAPIMetricsCollection{
		requestCount: requestCount,
	}, nil
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

	metrics hypixelAPIMetricsCollection
	tracer  trace.Tracer
}

func (hypixelAPI hypixelAPIImpl) GetPlayerData(ctx context.Context, uuid string) ([]byte, int, time.Time, error) {
	ctx, span := hypixelAPI.tracer.Start(ctx, "HypixelAPI.GetPlayerData")
	defer span.End()

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
	ran := hypixelAPI.limiter.Limit(ctx, getPlayerDataMinOperationTime, func(ctx context.Context) {
		ctx, span := hypixelAPI.tracer.Start(ctx, "HypixelAPI.get_data")
		defer span.End()

		requestCtx, span := hypixelAPI.tracer.Start(ctx, "HypixelAPI.make_request")
		defer span.End()

		resp, err = hypixelAPI.httpClient.Do(req)
		if err != nil {
			err := fmt.Errorf("failed to send request: %w", err)
			logger.Error(err.Error())
			reporting.Report(requestCtx, err)
			return
		}
		span.End()

		queriedAt = hypixelAPI.nowFunc()

		readAllCtx, span := hypixelAPI.tracer.Start(ctx, "HypixelAPI.read_response")
		defer span.End()

		defer resp.Body.Close()
		data, err = io.ReadAll(resp.Body)
		if err != nil {
			err := fmt.Errorf("failed to read response body: %w", err)
			logger.Error(err.Error())
			reporting.Report(readAllCtx, err)
			return
		}
		span.End()

		hypixelAPI.metrics.requestCount.Add(ctx, 1, metric.WithAttributes(
			attribute.String("status_code", fmt.Sprintf("%d", resp.StatusCode)),
		))
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
) (HypixelAPI, error) {
	const name = "flashlight/playerprovider"

	meter := otel.Meter(name)
	tracer := otel.Tracer(name)

	metrics, err := setupHypixelAPIMetrics(meter)
	if err != nil {
		return nil, fmt.Errorf("failed to set up metrics: %w", err)
	}

	limiter := ratelimiting.NewWindowLimitRequestLimiter(600, 5*time.Minute, nowFunc, afterFunc)
	return hypixelAPIImpl{
		httpClient: httpClient,
		limiter:    limiter,
		nowFunc:    nowFunc,
		apiKey:     apiKey,

		metrics: metrics,
		tracer:  tracer,
	}, nil
}

func NewHypixelAPIOrMock(
	config config.Config,
	httpClient HttpClient,
	nowFunc func() time.Time,
	afterFunc func(d time.Duration) <-chan time.Time,
) (HypixelAPI, error) {
	if config.HypixelAPIKey() != "" {
		api, err := NewHypixelAPI(httpClient, nowFunc, afterFunc, config.HypixelAPIKey())
		if err != nil {
			return nil, fmt.Errorf("failed to create Hypixel API: %w", err)
		}
		return api, nil
	}
	if config.IsDevelopment() {
		return &mockedHypixelAPI{}, nil
	}
	return nil, fmt.Errorf("Missing Hypixel API key in non-development environment")
}
