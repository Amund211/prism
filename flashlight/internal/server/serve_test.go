package server

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Amund211/flashlight/internal/domain"
	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/stretchr/testify/assert"
)

func TestMakeGetPlayerDataHandler(t *testing.T) {
	const UUID = "01234567-89ab-cdef-0123-456789abcdef"
	target := fmt.Sprintf("/?uuid=%s", UUID)

	t.Run("success", func(t *testing.T) {
		player := &domain.PlayerPIT{
			UUID:       UUID,
			Experience: 1000,
		}

		getPlayerDataHandler := MakeGetPlayerDataHandler(func(ctx context.Context, uuid string) (*domain.PlayerPIT, error) {
			return player, nil
		})

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
		})
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
		})
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
