package ports_test

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/ports"
	"github.com/stretchr/testify/require"
)

func TestMakeGetUUIDHandler(t *testing.T) {
	testLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	allowedOrigins, err := ports.NewDomainSuffixes("example.com", "test.com")
	require.NoError(t, err)
	noopMiddleware := func(h http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			h(w, r)
		}
	}

	makeGetUUID := func(t *testing.T, expectedUsername string, uuid string, err error) (app.GetUUID, *bool) {
		called := false
		return func(ctx context.Context, username string) (string, error) {
			t.Helper()
			require.Equal(t, expectedUsername, username)

			called = true

			return uuid, err
		}, &called
	}

	makeGetUUIDHandler := func(getUUID app.GetUUID) http.HandlerFunc {
		return ports.MakeGetUUIDHandler(
			getUUID,
			allowedOrigins,
			testLogger,
			noopMiddleware,
		)
	}

	username := "someguy"
	uuid := "01234567-89ab-cdef-0123-456789abcdef"
	successJSON := fmt.Sprintf(`{"success":true,"username":"someguy","uuid":"%s"}`, uuid)

	makeRequest := func(username string) *http.Request {
		req := httptest.NewRequest("GET", fmt.Sprintf("/v1/uuid/%s", username), nil)
		req.SetPathValue("username", username)
		return req
	}

	t.Run("successful get uuid", func(t *testing.T) {
		getUUIDFunc, called := makeGetUUID(t, username, uuid, nil)
		handler := makeGetUUIDHandler(getUUIDFunc)

		req := makeRequest(username)
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusOK, w.Code)
		body := w.Body.String()
		require.JSONEq(t, successJSON, body)
		require.True(t, *called)
		require.Equal(t, "application/json", w.Result().Header.Get("Content-Type"))
	})

	t.Run("username does not exist", func(t *testing.T) {
		getUUIDFunc, called := makeGetUUID(t, username, "", domain.ErrUsernameNotFound)
		handler := makeGetUUIDHandler(getUUIDFunc)

		req := makeRequest(username)
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusNotFound, w.Code)
		body := w.Body.String()
		require.NotContains(t, body, "uuid")
		require.True(t, *called)
		require.Equal(t, "application/json", w.Result().Header.Get("Content-Type"))
	})

	t.Run("temporarily unavailable", func(t *testing.T) {
		getUUIDFunc, called := makeGetUUID(t, username, "", domain.ErrTemporarilyUnavailable)
		handler := makeGetUUIDHandler(getUUIDFunc)

		req := makeRequest(username)
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusServiceUnavailable, w.Code)
		body := w.Body.String()
		require.NotContains(t, body, "uuid")
		require.True(t, *called)
		require.Equal(t, "application/json", w.Result().Header.Get("Content-Type"))
	})

	t.Run("invalid username length", func(t *testing.T) {
		getUUIDFunc, called := makeGetUUID(t, "", uuid, nil)
		handler := makeGetUUIDHandler(getUUIDFunc)

		req := makeRequest("")
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusBadRequest, w.Code)
		body := w.Body.String()
		require.Contains(t, body, "invalid username length")
		require.NotContains(t, body, "uuid")
		require.False(t, *called)
		require.Equal(t, "application/json", w.Result().Header.Get("Content-Type"))
	})

	t.Run("returns cors headers", func(t *testing.T) {
		getUUIDFunc, called := makeGetUUID(t, username, uuid, nil)
		handler := makeGetUUIDHandler(getUUIDFunc)

		origin := "https://subdomain.example.com"

		req := makeRequest(username)
		req.Header.Set("Origin", origin)
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusOK, w.Code)
		body := w.Body.String()
		require.JSONEq(t, successJSON, body)
		require.True(t, *called)

		resp := w.Result()
		require.Equal(t, "application/json", resp.Header.Get("Content-Type"))
		require.Equal(t, origin, resp.Header.Get("Access-Control-Allow-Origin"))
	})
}
