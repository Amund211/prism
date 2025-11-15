package tagprovider

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strconv"
	"time"

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

const getTagsMinOperationTime = 150 * time.Millisecond

type HttpClient interface {
	Do(req *http.Request) (*http.Response, error)
}

type RequestLimiter interface {
	Limit(ctx context.Context, minOperationTime time.Duration, operation func(ctx context.Context)) bool
}

type urchinAPIMetricsCollection struct {
	requestCount metric.Int64Counter
	returnCount  metric.Int64Counter
}

func setupUrchinAPIMetrics(meter metric.Meter) (urchinAPIMetricsCollection, error) {
	requestCount, err := meter.Int64Counter("tagprovider/urchin/request_count")
	if err != nil {
		return urchinAPIMetricsCollection{}, fmt.Errorf("failed to create request count metric: %w", err)
	}

	returnCount, err := meter.Int64Counter("tagprovider/urchin/return_count")
	if err != nil {
		return urchinAPIMetricsCollection{}, fmt.Errorf("failed to create return count metric: %w", err)
	}

	return urchinAPIMetricsCollection{
		requestCount: requestCount,
		returnCount:  returnCount,
	}, nil
}

type urchin struct {
	httpClient HttpClient
	limiter    RequestLimiter

	metrics urchinAPIMetricsCollection
	tracer  trace.Tracer
}

func NewUrchin(httpClient HttpClient, nowFunc func() time.Time, afterFunc func(time.Duration) <-chan time.Time) (*urchin, error) {
	const name = "flashlight/tagprovider/urchin"

	meter := otel.Meter(name)
	tracer := otel.Tracer(name)

	metrics, err := setupUrchinAPIMetrics(meter)
	if err != nil {
		return nil, fmt.Errorf("failed to set up metrics: %w", err)
	}

	// Just made one up
	limiter := ratelimiting.NewWindowLimitRequestLimiter(600, 5*time.Minute, nowFunc, afterFunc)

	return &urchin{
		httpClient: httpClient,
		limiter:    limiter,

		metrics: metrics,
		tracer:  tracer,
	}, nil
}

func (u *urchin) GetTags(ctx context.Context, uuid string, urchinAPIKey *string) (domain.Tags, error) {
	ctx, span := u.tracer.Start(ctx, "Urchin.GetTags")
	defer span.End()

	url := fmt.Sprintf("https://urchin.ws/player/%s?sources=MANUAL", uuid)
	if urchinAPIKey != nil {
		url += fmt.Sprintf("&key=%s", *urchinAPIKey)
	}

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		err := fmt.Errorf("failed to create request: %w", err)
		reporting.Report(ctx, err)
		return domain.Tags{}, err
	}

	req.Header.Set("User-Agent", constants.USER_AGENT)

	var resp *http.Response
	var data []byte
	logging.FromContext(ctx).InfoContext(ctx, "Context before Urchin HTTP GET", "ctx_error", ctx.Err())
	ran := u.limiter.Limit(ctx, getTagsMinOperationTime, func(ctx context.Context) {
		ctx, span := u.tracer.Start(ctx, "Urchin.httpget")
		defer span.End()

		resp, err = u.httpClient.Do(req)
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
		reporting.Report(ctx, fmt.Errorf("too many requests to urchin API"))
		logging.FromContext(ctx).WarnContext(ctx, "Did not run Urchin.GetTags due to rate limiting", "ctx_error", ctx.Err())
		return domain.Tags{}, fmt.Errorf("%w: too many requests to urchin API", domain.ErrTemporarilyUnavailable)
	}

	if err != nil {
		return domain.Tags{}, err
	}

	// Temporary logging to find examples of different cases
	logging.FromContext(ctx).InfoContext(
		ctx,
		"Got urchin response",
		slog.String("uuid", uuid),
		slog.String("data", string(data)),
	)

	tags, seen, err := tagsFromUrchinResponse(ctx, resp.StatusCode, data, urchinAPIKey != nil)
	if errors.Is(err, domain.ErrInvalidAPIKey) {
		// Don't report, as it is a client error
		return domain.Tags{}, err
	} else if err != nil {
		err := fmt.Errorf("failed to get tags from urchin response: %w", err)
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
		return domain.Tags{}, err
	}

	withAPIKey := urchinAPIKey != nil

	u.metrics.requestCount.Add(
		ctx,
		1,
		metric.WithAttributes(
			attribute.String("status_code", strconv.Itoa(resp.StatusCode)),
			attribute.Bool("tag_info", seen.info),
			attribute.Bool("tag_caution", seen.caution),
			attribute.Bool("tag_possible_sniper", seen.possibleSniper),
			attribute.Bool("tag_sniper", seen.sniper),
			attribute.Bool("tag_legit_sniper", seen.legitSniper),
			attribute.Bool("tag_closet_cheater", seen.closetCheater),
			attribute.Bool("tag_blatant_cheater", seen.blatantCheater),
			attribute.Bool("tag_confirmed_cheater", seen.confirmedCheater),
			attribute.Bool("tag_account", seen.account),
			attribute.Bool("with_api_key", withAPIKey),
		),
	)
	u.metrics.returnCount.Add(
		ctx,
		1,
		metric.WithAttributes(
			attribute.String("sniping_severity", tags.Sniping.String()),
			attribute.String("cheating_severity", tags.Cheating.String()),
			attribute.Bool("with_api_key", withAPIKey),
		),
	)

	return tags, nil
}

type urchinResponse struct {
	UUID string      `json:"uuid"`
	Tags []urchinTag `json:"tags"`
}

type urchinTag struct {
	Type urchinTagType `json:"type"`
}

type urchinTagType string

const (
	info             urchinTagType = "info"
	caution          urchinTagType = "caution"
	possibleSniper   urchinTagType = "possible_sniper"
	sniper           urchinTagType = "sniper"
	legitSniper      urchinTagType = "legit_sniper"
	closetCheater    urchinTagType = "closet_cheater"
	blatantCheater   urchinTagType = "blatant_cheater"
	confirmedCheater urchinTagType = "confirmed_cheater"
	account          urchinTagType = "account"
)

type urchinTagCollection struct {
	info             bool
	caution          bool
	possibleSniper   bool
	sniper           bool
	legitSniper      bool
	closetCheater    bool
	blatantCheater   bool
	confirmedCheater bool
	account          bool
}

func tagsFromUrchinResponse(ctx context.Context, statusCode int, data []byte, usedAPIKey bool) (domain.Tags, urchinTagCollection, error) {
	if usedAPIKey {
		if statusCode == http.StatusUnauthorized || statusCode == http.StatusForbidden {
			return domain.Tags{}, urchinTagCollection{}, fmt.Errorf("urchin API returned status code %d: %w", statusCode, domain.ErrInvalidAPIKey)
		}

		if len(data) < 100 && string(data) == `"Invalid Key"` {
			return domain.Tags{}, urchinTagCollection{}, fmt.Errorf("urchin API returned 'Invalid Key': %w", domain.ErrInvalidAPIKey)
		}
	}

	if statusCode != http.StatusOK {
		return domain.Tags{}, urchinTagCollection{}, fmt.Errorf("urchin API returned status code %d", statusCode)
	}

	var response urchinResponse
	if err := json.Unmarshal(data, &response); err != nil {
		return domain.Tags{}, urchinTagCollection{}, fmt.Errorf("failed to parse urchin response: %w", err)
	}

	// Temporary logging to find examples of different cases
	logging.FromContext(ctx).InfoContext(
		ctx,
		"Parsed urchin response",
		slog.Int("tag_count", len(response.Tags)),
	)

	tags := domain.Tags{}

	seenTags := urchinTagCollection{} // For metrics

	for _, urchinTag := range response.Tags {
		switch urchinTag.Type {
		case info:
			// Usually uninteresting messages
			seenTags.info = true
		case caution:
			// Some players tagged with caution have messages indicating cheating or sniping.
			// In other cases, it is totally unrelated stuff like "bow-spamming", "raging", etc.
			// It is also noted that legit players that toggle exclusively on other cheaters may get this tag.
			seenTags.caution = true
		case possibleSniper:
			tags = tags.AddSniping(domain.TagSeverityMedium).AddCheating(domain.TagSeverityMedium)
			seenTags.possibleSniper = true
		case sniper:
			tags = tags.AddSniping(domain.TagSeverityHigh).AddCheating(domain.TagSeverityMedium)
			seenTags.sniper = true
		case legitSniper:
			tags = tags.AddSniping(domain.TagSeverityHigh)
			seenTags.legitSniper = true
		case closetCheater:
			tags = tags.AddCheating(domain.TagSeverityMedium)
			seenTags.closetCheater = true
		case blatantCheater:
			tags = tags.AddCheating(domain.TagSeverityHigh)
			seenTags.blatantCheater = true
		case confirmedCheater:
			tags = tags.AddCheating(domain.TagSeverityHigh)
			seenTags.confirmedCheater = true
		case account:
			// Notes on the account, like "sold", "fake", etc.
			seenTags.account = true
		default:
			// Unknown tag type, ignore
			reporting.Report(
				ctx,
				fmt.Errorf("unknown urchin tag type: %s", urchinTag.Type),
				map[string]string{
					"uuid":          response.UUID,
					"response_data": string(data),
				},
			)
		}
	}

	return tags, seenTags, nil
}
