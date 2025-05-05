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
	"github.com/stretchr/testify/require"
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

		require.Equal(t, 200, resp.StatusCode)
		body := w.Body.String()

		require.Contains(t, body, UUID)
		require.Contains(t, body, `1000`)

		require.Equal(t, "application/json", resp.Header.Get("Content-Type"))
	})

	t.Run("client error: invalid uuid", func(t *testing.T) {
		getPlayerDataHandler := MakeGetPlayerDataHandler(func(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
			t.Helper()
			t.Fatal("should not be called")
			return nil, nil
		}, logger, sentryMiddleware)
		w := httptest.NewRecorder()

		req := httptest.NewRequest(http.MethodGet, "/?uuid=1234-1234-1234", nil)

		getPlayerDataHandler(w, req)

		resp := w.Result()
		require.Equal(t, 400, resp.StatusCode)
		require.Equal(t, `{"success":false,"cause":"Invalid UUID"}`, w.Body.String())
		require.Equal(t, "application/json", resp.Header.Get("Content-Type"))
	})

	t.Run("player not found", func(t *testing.T) {
		getPlayerDataHandler := MakeGetPlayerDataHandler(func(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
			return nil, fmt.Errorf("%w: couldn't find him", domain.ErrPlayerNotFound)
		}, logger, sentryMiddleware)
		w := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodGet, target, nil)

		getPlayerDataHandler(w, req)

		resp := w.Result()
		require.Equal(t, 404, resp.StatusCode)
		require.Equal(t, `{"success":true,"player":null}`, w.Body.String())
		require.Equal(t, "application/json", resp.Header.Get("Content-Type"))
	})

	t.Run("provider temporarily unavailable", func(t *testing.T) {
		getPlayerDataHandler := MakeGetPlayerDataHandler(func(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
			return nil, fmt.Errorf("error :^(: (%w)", domain.ErrTemporarilyUnavailable)
		}, logger, sentryMiddleware)
		w := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodGet, target, nil)

		getPlayerDataHandler(w, req)

		resp := w.Result()
		require.Equal(t, 504, resp.StatusCode)
		require.Equal(t, `{"success":false,"cause":"error :^(: (temporarily unavailable)"}`, w.Body.String())
		require.Equal(t, "application/json", resp.Header.Get("Content-Type"))
	})

	t.Run("rate limit exceeded", func(t *testing.T) {
		player := &domain.PlayerPIT{
			UUID:       UUID,
			Experience: 1000,
		}

		getPlayerDataHandler := MakeGetPlayerDataHandler(func(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
			return player, nil
		}, logger, sentryMiddleware)

		// Exhaust the rate limit
		for i := 0; i < 200; i++ {
			w := httptest.NewRecorder()
			req := httptest.NewRequest(http.MethodGet, target, nil)
			getPlayerDataHandler(w, req)

			resp := w.Result()
			if resp.StatusCode != 200 {
				require.Equal(t, 429, resp.StatusCode)
				break
			}
		}

		for i := 0; i < 30; i++ {
			w := httptest.NewRecorder()
			req := httptest.NewRequest(http.MethodGet, target, nil)
			getPlayerDataHandler(w, req)

			resp := w.Result()
			if resp.StatusCode != 429 {
				// We may have gotten some credits back so this request could go through
				require.Equal(t, 200, resp.StatusCode)
				continue
			}

			require.Equal(t, 429, resp.StatusCode)
			require.Equal(t, `{"success":false,"cause":"Rate limit exceeded"}`, w.Body.String())
			require.Equal(t, "application/json", resp.Header.Get("Content-Type"))
			return
		}

		require.Fail(t, "Rate limit not exceeded")
	})
}

func TestWriteErrorResponse(t *testing.T) {
	testCases := []struct {
		err            error
		expectedStatus int
		expectedBody   string
	}{
		{
			err:            fmt.Errorf("something happened"),
			expectedStatus: 500,
			expectedBody:   `{"success":false,"cause":"something happened"}`,
		},
		{
			err:            fmt.Errorf("something happened (%w)", domain.ErrTemporarilyUnavailable),
			expectedStatus: 504,
			expectedBody:   `{"success":false,"cause":"something happened (temporarily unavailable)"}`,
		},
		{
			// NOTE: We don't pass player not found to write error response
			err:            fmt.Errorf("%w: never heard of him", domain.ErrPlayerNotFound),
			expectedStatus: 500,
			expectedBody:   `{"success":false,"cause":"player not found: never heard of him"}`,
		},
	}

	expectedHeaders := make(http.Header)
	expectedHeaders.Set("Content-Type", "application/json")

	for _, testCase := range testCases {
		w := httptest.NewRecorder()

		returnedStatusCode := writeHypixelStyleErrorResponse(context.Background(), w, testCase.err)
		result := w.Result()

		require.True(t, reflect.DeepEqual(expectedHeaders, result.Header), "Expected %v, got %v", expectedHeaders, result.Header)

		require.Equal(t, testCase.expectedStatus, result.StatusCode)
		require.Equal(t, testCase.expectedStatus, returnedStatusCode)

		body := w.Body.String()
		require.Equal(t, testCase.expectedBody, body)
	}
}
