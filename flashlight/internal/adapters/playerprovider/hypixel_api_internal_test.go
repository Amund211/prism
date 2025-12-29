package playerprovider

import (
	"bytes"
	"context"
	"io"
	"net/http"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/metric/embedded"
	tracenoop "go.opentelemetry.io/otel/trace/noop"
)

// mockMeter is a test meter that tracks metric recordings
type mockMeter struct {
	embedded.Meter
	gauges   map[string]*mockGauge
	counters map[string]*mockCounter
}

func newMockMeter() *mockMeter {
	return &mockMeter{
		gauges:   make(map[string]*mockGauge),
		counters: make(map[string]*mockCounter),
	}
}

func (m *mockMeter) Int64Counter(name string, options ...metric.Int64CounterOption) (metric.Int64Counter, error) {
	counter := &mockCounter{name: name}
	m.counters[name] = counter
	return counter, nil
}

func (m *mockMeter) Int64UpDownCounter(name string, options ...metric.Int64UpDownCounterOption) (metric.Int64UpDownCounter, error) {
	return nil, nil
}

func (m *mockMeter) Int64Histogram(name string, options ...metric.Int64HistogramOption) (metric.Int64Histogram, error) {
	return nil, nil
}

func (m *mockMeter) Int64Gauge(name string, options ...metric.Int64GaugeOption) (metric.Int64Gauge, error) {
	gauge := &mockGauge{name: name}
	m.gauges[name] = gauge
	return gauge, nil
}

func (m *mockMeter) Int64ObservableCounter(name string, options ...metric.Int64ObservableCounterOption) (metric.Int64ObservableCounter, error) {
	return nil, nil
}

func (m *mockMeter) Int64ObservableUpDownCounter(name string, options ...metric.Int64ObservableUpDownCounterOption) (metric.Int64ObservableUpDownCounter, error) {
	return nil, nil
}

func (m *mockMeter) Int64ObservableGauge(name string, options ...metric.Int64ObservableGaugeOption) (metric.Int64ObservableGauge, error) {
	return nil, nil
}

func (m *mockMeter) Float64Counter(name string, options ...metric.Float64CounterOption) (metric.Float64Counter, error) {
	return nil, nil
}

func (m *mockMeter) Float64UpDownCounter(name string, options ...metric.Float64UpDownCounterOption) (metric.Float64UpDownCounter, error) {
	return nil, nil
}

func (m *mockMeter) Float64Histogram(name string, options ...metric.Float64HistogramOption) (metric.Float64Histogram, error) {
	return nil, nil
}

func (m *mockMeter) Float64Gauge(name string, options ...metric.Float64GaugeOption) (metric.Float64Gauge, error) {
	return nil, nil
}

func (m *mockMeter) Float64ObservableCounter(name string, options ...metric.Float64ObservableCounterOption) (metric.Float64ObservableCounter, error) {
	return nil, nil
}

func (m *mockMeter) Float64ObservableUpDownCounter(name string, options ...metric.Float64ObservableUpDownCounterOption) (metric.Float64ObservableUpDownCounter, error) {
	return nil, nil
}

func (m *mockMeter) Float64ObservableGauge(name string, options ...metric.Float64ObservableGaugeOption) (metric.Float64ObservableGauge, error) {
	return nil, nil
}

func (m *mockMeter) RegisterCallback(callback metric.Callback, instruments ...metric.Observable) (metric.Registration, error) {
	return nil, nil
}

// mockGauge tracks Int64Gauge recordings
type mockGauge struct {
	embedded.Int64Gauge
	name       string
	lastValue  int64
	recorded   bool
	attributes []attribute.KeyValue
}

func (g *mockGauge) Record(ctx context.Context, value int64, options ...metric.RecordOption) {
	g.lastValue = value
	g.recorded = true

	cfg := metric.NewRecordConfig(options)
	attrs := cfg.Attributes()
	iter := attrs.Iter()
	g.attributes = nil
	for iter.Next() {
		g.attributes = append(g.attributes, iter.Attribute())
	}
}

// mockCounter tracks Int64Counter recordings
type mockCounter struct {
	embedded.Int64Counter
	name       string
	lastValue  int64
	recorded   bool
	attributes []attribute.KeyValue
}

func (c *mockCounter) Add(ctx context.Context, value int64, options ...metric.AddOption) {
	c.lastValue += value
	c.recorded = true

	cfg := metric.NewAddConfig(options)
	attrs := cfg.Attributes()
	iter := attrs.Iter()
	c.attributes = nil
	for iter.Next() {
		c.attributes = append(c.attributes, iter.Attribute())
	}
}

// mockRequestLimiter is a simple limiter that always allows requests
type mockRequestLimiter struct{}

func (l *mockRequestLimiter) Limit(ctx context.Context, minOperationTime time.Duration, operation func(ctx context.Context)) bool {
	operation(ctx)
	return true
}

func TestGetPlayerDataRateLimitHeaders(t *testing.T) {
	t.Parallel()

	now := time.Now()
	nowFunc := func() time.Time {
		return now
	}

	// Test with both headers present (real response sample based on docs)
	t.Run("both headers present", func(t *testing.T) {
		t.Parallel()

		mockMeter := newMockMeter()

		headers := http.Header{}
		headers.Set("RateLimit-Limit", "120")
		headers.Set("RateLimit-Remaining", "100")

		httpClient := &mockedHttpClient{
			t:           t,
			expectedURL: "https://api.hypixel.net/v2/player?uuid=test-uuid-1",
			response: &http.Response{
				StatusCode: 200,
				Header:     headers,
				Body:       io.NopCloser(bytes.NewBufferString(`{"success":true,"player":null}`)),
			},
		}

		metrics, err := setupHypixelAPIMetrics(mockMeter)
		require.NoError(t, err)

		api := hypixelAPIImpl{
			httpClient: httpClient,
			limiter:    &mockRequestLimiter{},
			nowFunc:    nowFunc,
			apiKey:     apiKey,
			metrics:    metrics,
			tracer:     tracenoop.NewTracerProvider().Tracer("test"),
		}

		_, statusCode, _, err := api.GetPlayerData(context.Background(), "test-uuid-1")

		require.NoError(t, err)
		require.Equal(t, 200, statusCode)

		// Verify metrics were recorded
		limitGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_limit"]
		require.NotNil(t, limitGauge)
		require.True(t, limitGauge.recorded, "rate_limit_limit gauge should be recorded")
		require.Equal(t, int64(120), limitGauge.lastValue)

		remainingGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_remaining"]
		require.NotNil(t, remainingGauge)
		require.True(t, remainingGauge.recorded, "rate_limit_remaining gauge should be recorded")
		require.Equal(t, int64(100), remainingGauge.lastValue)

		spentGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_spent"]
		require.NotNil(t, spentGauge)
		require.True(t, spentGauge.recorded, "rate_limit_spent gauge should be recorded")
		require.Equal(t, int64(20), spentGauge.lastValue, "spent should be limit - remaining = 120 - 100 = 20")
	})

	// Test with only limit header present
	t.Run("only limit header present", func(t *testing.T) {
		t.Parallel()

		mockMeter := newMockMeter()

		headers := http.Header{}
		headers.Set("RateLimit-Limit", "120")

		httpClient := &mockedHttpClient{
			t:           t,
			expectedURL: "https://api.hypixel.net/v2/player?uuid=test-uuid-2",
			response: &http.Response{
				StatusCode: 200,
				Header:     headers,
				Body:       io.NopCloser(bytes.NewBufferString(`{"success":true,"player":null}`)),
			},
		}

		metrics, err := setupHypixelAPIMetrics(mockMeter)
		require.NoError(t, err)

		api := hypixelAPIImpl{
			httpClient: httpClient,
			limiter:    &mockRequestLimiter{},
			nowFunc:    nowFunc,
			apiKey:     apiKey,
			metrics:    metrics,
			tracer:     tracenoop.NewTracerProvider().Tracer("test"),
		}

		_, statusCode, _, err := api.GetPlayerData(context.Background(), "test-uuid-2")

		require.NoError(t, err)
		require.Equal(t, 200, statusCode)

		// Verify only limit was recorded
		limitGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_limit"]
		require.NotNil(t, limitGauge)
		require.True(t, limitGauge.recorded, "rate_limit_limit gauge should be recorded")
		require.Equal(t, int64(120), limitGauge.lastValue)

		remainingGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_remaining"]
		require.NotNil(t, remainingGauge)
		require.False(t, remainingGauge.recorded, "rate_limit_remaining gauge should not be recorded")

		spentGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_spent"]
		require.NotNil(t, spentGauge)
		require.False(t, spentGauge.recorded, "rate_limit_spent gauge should not be recorded without both headers")
	})

	// Test with only remaining header present
	t.Run("only remaining header present", func(t *testing.T) {
		t.Parallel()

		mockMeter := newMockMeter()

		headers := http.Header{}
		headers.Set("RateLimit-Remaining", "100")

		httpClient := &mockedHttpClient{
			t:           t,
			expectedURL: "https://api.hypixel.net/v2/player?uuid=test-uuid-3",
			response: &http.Response{
				StatusCode: 200,
				Header:     headers,
				Body:       io.NopCloser(bytes.NewBufferString(`{"success":true,"player":null}`)),
			},
		}

		metrics, err := setupHypixelAPIMetrics(mockMeter)
		require.NoError(t, err)

		api := hypixelAPIImpl{
			httpClient: httpClient,
			limiter:    &mockRequestLimiter{},
			nowFunc:    nowFunc,
			apiKey:     apiKey,
			metrics:    metrics,
			tracer:     tracenoop.NewTracerProvider().Tracer("test"),
		}

		_, statusCode, _, err := api.GetPlayerData(context.Background(), "test-uuid-3")

		require.NoError(t, err)
		require.Equal(t, 200, statusCode)

		// Verify only remaining was recorded
		limitGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_limit"]
		require.NotNil(t, limitGauge)
		require.False(t, limitGauge.recorded, "rate_limit_limit gauge should not be recorded")

		remainingGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_remaining"]
		require.NotNil(t, remainingGauge)
		require.True(t, remainingGauge.recorded, "rate_limit_remaining gauge should be recorded")
		require.Equal(t, int64(100), remainingGauge.lastValue)

		spentGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_spent"]
		require.NotNil(t, spentGauge)
		require.False(t, spentGauge.recorded, "rate_limit_spent gauge should not be recorded without both headers")
	})

	// Test with no rate limit headers
	t.Run("no rate limit headers", func(t *testing.T) {
		t.Parallel()

		mockMeter := newMockMeter()

		headers := http.Header{}

		httpClient := &mockedHttpClient{
			t:           t,
			expectedURL: "https://api.hypixel.net/v2/player?uuid=test-uuid-4",
			response: &http.Response{
				StatusCode: 200,
				Header:     headers,
				Body:       io.NopCloser(bytes.NewBufferString(`{"success":true,"player":null}`)),
			},
		}

		metrics, err := setupHypixelAPIMetrics(mockMeter)
		require.NoError(t, err)

		api := hypixelAPIImpl{
			httpClient: httpClient,
			limiter:    &mockRequestLimiter{},
			nowFunc:    nowFunc,
			apiKey:     apiKey,
			metrics:    metrics,
			tracer:     tracenoop.NewTracerProvider().Tracer("test"),
		}

		_, statusCode, _, err := api.GetPlayerData(context.Background(), "test-uuid-4")

		require.NoError(t, err)
		require.Equal(t, 200, statusCode)

		// Verify no gauges were recorded
		limitGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_limit"]
		require.NotNil(t, limitGauge)
		require.False(t, limitGauge.recorded, "rate_limit_limit gauge should not be recorded")

		remainingGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_remaining"]
		require.NotNil(t, remainingGauge)
		require.False(t, remainingGauge.recorded, "rate_limit_remaining gauge should not be recorded")

		spentGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_spent"]
		require.NotNil(t, spentGauge)
		require.False(t, spentGauge.recorded, "rate_limit_spent gauge should not be recorded")
	})

	// Test with invalid limit header value
	t.Run("invalid limit header value", func(t *testing.T) {
		t.Parallel()

		mockMeter := newMockMeter()

		headers := http.Header{}
		headers.Set("RateLimit-Limit", "invalid")
		headers.Set("RateLimit-Remaining", "100")

		httpClient := &mockedHttpClient{
			t:           t,
			expectedURL: "https://api.hypixel.net/v2/player?uuid=test-uuid-5",
			response: &http.Response{
				StatusCode: 200,
				Header:     headers,
				Body:       io.NopCloser(bytes.NewBufferString(`{"success":true,"player":null}`)),
			},
		}

		metrics, err := setupHypixelAPIMetrics(mockMeter)
		require.NoError(t, err)

		api := hypixelAPIImpl{
			httpClient: httpClient,
			limiter:    &mockRequestLimiter{},
			nowFunc:    nowFunc,
			apiKey:     apiKey,
			metrics:    metrics,
			tracer:     tracenoop.NewTracerProvider().Tracer("test"),
		}

		// Should not crash
		_, statusCode, _, err := api.GetPlayerData(context.Background(), "test-uuid-5")

		require.NoError(t, err)
		require.Equal(t, 200, statusCode)

		// Verify limit was not recorded but remaining was
		limitGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_limit"]
		require.NotNil(t, limitGauge)
		require.False(t, limitGauge.recorded, "rate_limit_limit gauge should not be recorded with invalid value")

		remainingGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_remaining"]
		require.NotNil(t, remainingGauge)
		require.True(t, remainingGauge.recorded, "rate_limit_remaining gauge should be recorded")
		require.Equal(t, int64(100), remainingGauge.lastValue)

		spentGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_spent"]
		require.NotNil(t, spentGauge)
		require.False(t, spentGauge.recorded, "rate_limit_spent gauge should not be recorded without valid limit")
	})

	// Test with invalid remaining header value
	t.Run("invalid remaining header value", func(t *testing.T) {
		t.Parallel()

		mockMeter := newMockMeter()

		headers := http.Header{}
		headers.Set("RateLimit-Limit", "120")
		headers.Set("RateLimit-Remaining", "not-a-number")

		httpClient := &mockedHttpClient{
			t:           t,
			expectedURL: "https://api.hypixel.net/v2/player?uuid=test-uuid-6",
			response: &http.Response{
				StatusCode: 200,
				Header:     headers,
				Body:       io.NopCloser(bytes.NewBufferString(`{"success":true,"player":null}`)),
			},
		}

		metrics, err := setupHypixelAPIMetrics(mockMeter)
		require.NoError(t, err)

		api := hypixelAPIImpl{
			httpClient: httpClient,
			limiter:    &mockRequestLimiter{},
			nowFunc:    nowFunc,
			apiKey:     apiKey,
			metrics:    metrics,
			tracer:     tracenoop.NewTracerProvider().Tracer("test"),
		}

		// Should not crash
		_, statusCode, _, err := api.GetPlayerData(context.Background(), "test-uuid-6")

		require.NoError(t, err)
		require.Equal(t, 200, statusCode)

		// Verify limit was recorded but remaining was not
		limitGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_limit"]
		require.NotNil(t, limitGauge)
		require.True(t, limitGauge.recorded, "rate_limit_limit gauge should be recorded")
		require.Equal(t, int64(120), limitGauge.lastValue)

		remainingGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_remaining"]
		require.NotNil(t, remainingGauge)
		require.False(t, remainingGauge.recorded, "rate_limit_remaining gauge should not be recorded with invalid value")

		spentGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_spent"]
		require.NotNil(t, spentGauge)
		require.False(t, spentGauge.recorded, "rate_limit_spent gauge should not be recorded without valid remaining")
	})

	// Test with both invalid header values
	t.Run("both invalid header values", func(t *testing.T) {
		t.Parallel()

		mockMeter := newMockMeter()

		headers := http.Header{}
		headers.Set("RateLimit-Limit", "abc")
		headers.Set("RateLimit-Remaining", "xyz")

		httpClient := &mockedHttpClient{
			t:           t,
			expectedURL: "https://api.hypixel.net/v2/player?uuid=test-uuid-7",
			response: &http.Response{
				StatusCode: 200,
				Header:     headers,
				Body:       io.NopCloser(bytes.NewBufferString(`{"success":true,"player":null}`)),
			},
		}

		metrics, err := setupHypixelAPIMetrics(mockMeter)
		require.NoError(t, err)

		api := hypixelAPIImpl{
			httpClient: httpClient,
			limiter:    &mockRequestLimiter{},
			nowFunc:    nowFunc,
			apiKey:     apiKey,
			metrics:    metrics,
			tracer:     tracenoop.NewTracerProvider().Tracer("test"),
		}

		// Should not crash
		_, statusCode, _, err := api.GetPlayerData(context.Background(), "test-uuid-7")

		require.NoError(t, err)
		require.Equal(t, 200, statusCode)

		// Verify no gauges were recorded
		limitGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_limit"]
		require.NotNil(t, limitGauge)
		require.False(t, limitGauge.recorded, "rate_limit_limit gauge should not be recorded with invalid value")

		remainingGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_remaining"]
		require.NotNil(t, remainingGauge)
		require.False(t, remainingGauge.recorded, "rate_limit_remaining gauge should not be recorded with invalid value")

		spentGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_spent"]
		require.NotNil(t, spentGauge)
		require.False(t, spentGauge.recorded, "rate_limit_spent gauge should not be recorded")
	})

	// Test with negative values
	t.Run("negative header values", func(t *testing.T) {
		t.Parallel()

		mockMeter := newMockMeter()

		headers := http.Header{}
		headers.Set("RateLimit-Limit", "-10")
		headers.Set("RateLimit-Remaining", "-5")

		httpClient := &mockedHttpClient{
			t:           t,
			expectedURL: "https://api.hypixel.net/v2/player?uuid=test-uuid-8",
			response: &http.Response{
				StatusCode: 200,
				Header:     headers,
				Body:       io.NopCloser(bytes.NewBufferString(`{"success":true,"player":null}`)),
			},
		}

		metrics, err := setupHypixelAPIMetrics(mockMeter)
		require.NoError(t, err)

		api := hypixelAPIImpl{
			httpClient: httpClient,
			limiter:    &mockRequestLimiter{},
			nowFunc:    nowFunc,
			apiKey:     apiKey,
			metrics:    metrics,
			tracer:     tracenoop.NewTracerProvider().Tracer("test"),
		}

		// Should not crash
		_, statusCode, _, err := api.GetPlayerData(context.Background(), "test-uuid-8")

		require.NoError(t, err)
		require.Equal(t, 200, statusCode)

		// Verify negative values are recorded (parsing succeeds)
		limitGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_limit"]
		require.NotNil(t, limitGauge)
		require.True(t, limitGauge.recorded, "rate_limit_limit gauge should be recorded even with negative value")
		require.Equal(t, int64(-10), limitGauge.lastValue)

		remainingGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_remaining"]
		require.NotNil(t, remainingGauge)
		require.True(t, remainingGauge.recorded, "rate_limit_remaining gauge should be recorded even with negative value")
		require.Equal(t, int64(-5), remainingGauge.lastValue)

		spentGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_spent"]
		require.NotNil(t, spentGauge)
		require.True(t, spentGauge.recorded, "rate_limit_spent gauge should be recorded")
		require.Equal(t, int64(-5), spentGauge.lastValue, "spent = -10 - (-5) = -5")
	})

	// Test with zero values
	t.Run("zero header values", func(t *testing.T) {
		t.Parallel()

		mockMeter := newMockMeter()

		headers := http.Header{}
		headers.Set("RateLimit-Limit", "0")
		headers.Set("RateLimit-Remaining", "0")

		httpClient := &mockedHttpClient{
			t:           t,
			expectedURL: "https://api.hypixel.net/v2/player?uuid=test-uuid-9",
			response: &http.Response{
				StatusCode: 200,
				Header:     headers,
				Body:       io.NopCloser(bytes.NewBufferString(`{"success":true,"player":null}`)),
			},
		}

		metrics, err := setupHypixelAPIMetrics(mockMeter)
		require.NoError(t, err)

		api := hypixelAPIImpl{
			httpClient: httpClient,
			limiter:    &mockRequestLimiter{},
			nowFunc:    nowFunc,
			apiKey:     apiKey,
			metrics:    metrics,
			tracer:     tracenoop.NewTracerProvider().Tracer("test"),
		}

		_, statusCode, _, err := api.GetPlayerData(context.Background(), "test-uuid-9")

		require.NoError(t, err)
		require.Equal(t, 200, statusCode)

		// Verify zero values are recorded
		limitGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_limit"]
		require.NotNil(t, limitGauge)
		require.True(t, limitGauge.recorded, "rate_limit_limit gauge should be recorded")
		require.Equal(t, int64(0), limitGauge.lastValue)

		remainingGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_remaining"]
		require.NotNil(t, remainingGauge)
		require.True(t, remainingGauge.recorded, "rate_limit_remaining gauge should be recorded")
		require.Equal(t, int64(0), remainingGauge.lastValue)

		spentGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_spent"]
		require.NotNil(t, spentGauge)
		require.True(t, spentGauge.recorded, "rate_limit_spent gauge should be recorded")
		require.Equal(t, int64(0), spentGauge.lastValue)
	})

	// Test with very large values
	t.Run("large header values", func(t *testing.T) {
		t.Parallel()

		mockMeter := newMockMeter()

		headers := http.Header{}
		headers.Set("RateLimit-Limit", "9223372036854775807") // max int64
		headers.Set("RateLimit-Remaining", "9223372036854775806")

		httpClient := &mockedHttpClient{
			t:           t,
			expectedURL: "https://api.hypixel.net/v2/player?uuid=test-uuid-10",
			response: &http.Response{
				StatusCode: 200,
				Header:     headers,
				Body:       io.NopCloser(bytes.NewBufferString(`{"success":true,"player":null}`)),
			},
		}

		metrics, err := setupHypixelAPIMetrics(mockMeter)
		require.NoError(t, err)

		api := hypixelAPIImpl{
			httpClient: httpClient,
			limiter:    &mockRequestLimiter{},
			nowFunc:    nowFunc,
			apiKey:     apiKey,
			metrics:    metrics,
			tracer:     tracenoop.NewTracerProvider().Tracer("test"),
		}

		_, statusCode, _, err := api.GetPlayerData(context.Background(), "test-uuid-10")

		require.NoError(t, err)
		require.Equal(t, 200, statusCode)

		// Verify large values are recorded
		limitGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_limit"]
		require.NotNil(t, limitGauge)
		require.True(t, limitGauge.recorded, "rate_limit_limit gauge should be recorded")
		require.Equal(t, int64(9223372036854775807), limitGauge.lastValue)

		remainingGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_remaining"]
		require.NotNil(t, remainingGauge)
		require.True(t, remainingGauge.recorded, "rate_limit_remaining gauge should be recorded")
		require.Equal(t, int64(9223372036854775806), remainingGauge.lastValue)

		spentGauge := mockMeter.gauges["playerprovider/hypixel_api/rate_limit_spent"]
		require.NotNil(t, spentGauge)
		require.True(t, spentGauge.recorded, "rate_limit_spent gauge should be recorded")
		require.Equal(t, int64(1), spentGauge.lastValue)
	})
}
