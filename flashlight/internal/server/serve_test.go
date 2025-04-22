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
	t.Run("success", func(t *testing.T) {
		getPlayerDataHandler := MakeGetPlayerDataHandler(func(ctx context.Context, uuid string) (domain.PlayerResponse, error) {
			return domain.PlayerResponse{Data: []byte(`data`), StatusCode: 200}, nil
		})
		w := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodGet, "/?uuid=uuid1234", nil)
		getPlayerDataHandler(w, req)

		resp := w.Result()

		assert.Equal(t, 200, resp.StatusCode)
		assert.Equal(t, `data`, w.Body.String())
		contentType := resp.Header.Get("Content-Type")
		assert.Equal(t, "application/json", contentType)
	})

	t.Run("client error", func(t *testing.T) {
		getPlayerDataHandler := MakeGetPlayerDataHandler(func(ctx context.Context, uuid string) (domain.PlayerResponse, error) {
			return domain.PlayerResponse{}, fmt.Errorf("%w: error :^)", e.APIClientError)
		})
		w := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodGet, "/?uuid=uuid1234", nil)

		getPlayerDataHandler(w, req)

		resp := w.Result()
		assert.Equal(t, 400, resp.StatusCode)
		assert.Equal(t, `{"success":false,"cause":"Client error: error :^)"}`, w.Body.String())
		contentType := resp.Header.Get("Content-Type")
		assert.Equal(t, "application/json", contentType)
	})

	t.Run("server error", func(t *testing.T) {
		getPlayerDataHandler := MakeGetPlayerDataHandler(func(ctx context.Context, uuid string) (domain.PlayerResponse, error) {
			return domain.PlayerResponse{}, fmt.Errorf("%w: error :^(", e.APIServerError)
		})
		w := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodGet, "/?uuid=uuid1234", nil)

		getPlayerDataHandler(w, req)

		resp := w.Result()
		assert.Equal(t, 500, resp.StatusCode)
		assert.Equal(t, `{"success":false,"cause":"Server error: error :^("}`, w.Body.String())
		contentType := resp.Header.Get("Content-Type")
		assert.Equal(t, "application/json", contentType)
	})
}
