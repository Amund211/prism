package ports

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"reflect"
	"testing"

	"github.com/Amund211/flashlight/internal/domain"
	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/stretchr/testify/assert"
)

func TestMakeGetPlayerDataHandler(t *testing.T) {
	const UUID = "01234567-89ab-cdef-0123-456789abcdef"
	target := fmt.Sprintf("/?uuid=%s", UUID)

	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	sentryMiddleware := func(next http.HandlerFunc) http.HandlerFunc {
		return next
	}

	t.Run("success", func(t *testing.T) {
		player := &domain.PlayerPIT{
			UUID:       UUID,
			Experience: 1000,
		}

		getPlayerDataHandler := MakeGetPlayerDataHandler(func(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
			return player, nil
		}, logger, sentryMiddleware)

		w := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodGet, target, nil)
		getPlayerDataHandler(w, req)

		resp := w.Result()

		assert.Equal(t, 200, resp.StatusCode)
		body := w.Body.String()

		assert.Contains(t, body, UUID)
		assert.Contains(t, body, `1000`)

		contentType := resp.Header.Get("Content-Type")
		assert.Equal(t, "application/json", contentType)
	})

	t.Run("client error", func(t *testing.T) {
		getPlayerDataHandler := MakeGetPlayerDataHandler(func(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
			return nil, fmt.Errorf("%w: error :^)", e.APIClientError)
		}, logger, sentryMiddleware)
		w := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodGet, target, nil)

		getPlayerDataHandler(w, req)

		resp := w.Result()
		assert.Equal(t, 400, resp.StatusCode)
		assert.Equal(t, `{"success":false,"cause":"Client error: error :^)"}`, w.Body.String())
		contentType := resp.Header.Get("Content-Type")
		assert.Equal(t, "application/json", contentType)
	})

	t.Run("server error", func(t *testing.T) {
		getPlayerDataHandler := MakeGetPlayerDataHandler(func(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
			return nil, fmt.Errorf("%w: error :^(", e.APIServerError)
		}, logger, sentryMiddleware)
		w := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodGet, target, nil)

		getPlayerDataHandler(w, req)

		resp := w.Result()
		assert.Equal(t, 500, resp.StatusCode)
		assert.Equal(t, `{"success":false,"cause":"Server error: error :^("}`, w.Body.String())
		contentType := resp.Header.Get("Content-Type")
		assert.Equal(t, "application/json", contentType)
	})
}

func TestWriteErrorResponse(t *testing.T) {
	testCases := []struct {
		err            error
		expectedStatus int
		expectedBody   string
	}{
		{
			err:            e.APIServerError,
			expectedStatus: 500,
			expectedBody:   `{"success":false,"cause":"Server error"}`,
		},
		{
			err:            e.APIClientError,
			expectedStatus: 400,
			expectedBody:   `{"success":false,"cause":"Client error"}`,
		},
		{
			err:            e.RatelimitExceededError,
			expectedStatus: 429,
			expectedBody:   `{"success":false,"cause":"Ratelimit exceeded"}`,
		},
		{
			err:            fmt.Errorf("something happened %w", e.RetriableError),
			expectedStatus: 504,
			expectedBody:   `{"success":false,"cause":"something happened (retriable)"}`,
		},
		{
			err:            fmt.Errorf("%w %w", e.RatelimitExceededError, e.RetriableError),
			expectedStatus: 429,
			expectedBody:   `{"success":false,"cause":"Ratelimit exceeded (retriable)"}`,
		},
	}

	expectedHeaders := make(http.Header)
	expectedHeaders.Set("Content-Type", "application/json")

	for _, testCase := range testCases {
		w := httptest.NewRecorder()

		returnedStatusCode := writeHypixelStyleErrorResponse(context.Background(), w, testCase.err)
		result := w.Result()

		assert.True(t, reflect.DeepEqual(expectedHeaders, result.Header), "Expected %v, got %v", expectedHeaders, result.Header)

		assert.Equal(t, testCase.expectedStatus, result.StatusCode)
		assert.Equal(t, testCase.expectedStatus, returnedStatusCode)

		body := w.Body.String()
		assert.Equal(t, testCase.expectedBody, body)
	}
}
