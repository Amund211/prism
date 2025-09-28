package ports_test

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/ports"
	"github.com/stretchr/testify/require"
)

func TestMakeGetAccountByUUIDHandler(t *testing.T) {
	t.Parallel()

	testLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	allowedOrigins, err := ports.NewDomainSuffixes("example.com", "test.com")
	require.NoError(t, err)
	noopMiddleware := func(h http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			h(w, r)
		}
	}

	makeGetAccountByUUID := func(t *testing.T, expectedUUID string, account domain.Account, err error) (app.GetAccountByUUID, *bool) {
		called := false
		return func(ctx context.Context, uuid string) (domain.Account, error) {
			t.Helper()
			require.Equal(t, expectedUUID, uuid)

			called = true

			return account, err
		}, &called
	}

	makeGetAccountByUUIDHandler := func(getAccountByUUID app.GetAccountByUUID) http.HandlerFunc {
		return ports.MakeGetAccountByUUIDHandler(
			getAccountByUUID,
			allowedOrigins,
			testLogger,
			noopMiddleware,
		)
	}

	uuid := "01234567-89ab-cdef-0123-456789abcdef"
	successJSON := fmt.Sprintf(`{"success":true,"username":"SomeGuy","uuid":"%s"}`, uuid)

	type response struct {
		Success  *bool   `json:"success"`
		Username *string `json:"username"`
		UUID     *string `json:"uuid"`
		Cause    *string `json:"cause"`
	}

	parseResponse := func(t *testing.T, body string) response {
		var resp response
		err := json.Unmarshal([]byte(body), &resp)
		require.NoError(t, err)
		return resp
	}

	makeRequest := func(uuid string) *http.Request {
		req := httptest.NewRequest("GET", fmt.Sprintf("/v1/account/uuid/%s", uuid), nil)
		req.SetPathValue("uuid", uuid)
		return req
	}

	now := time.Now()

	t.Run("successful get by uuid", func(t *testing.T) {
		t.Parallel()

		getAccountByUUID, called := makeGetAccountByUUID(t, uuid, domain.Account{
			Username:  "SomeGuy",
			UUID:      uuid,
			QueriedAt: now.Add(-time.Hour),
		}, nil)
		handler := makeGetAccountByUUIDHandler(getAccountByUUID)

		req := makeRequest(uuid)
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusOK, w.Code)
		body := w.Body.String()
		require.JSONEq(t, successJSON, body)
		parsed := parseResponse(t, body)
		require.NotNil(t, parsed.Success)
		require.True(t, *parsed.Success)
		require.NotNil(t, parsed.UUID)
		require.Equal(t, uuid, *parsed.UUID)
		require.Nil(t, parsed.Cause)
		require.NotNil(t, parsed.Username)
		require.Equal(t, "SomeGuy", *parsed.Username)

		require.True(t, *called)
		require.Equal(t, "application/json", w.Result().Header.Get("Content-Type"))
	})

	t.Run("uuid is normalized", func(t *testing.T) {
		t.Parallel()

		getAccountByUUID, called := makeGetAccountByUUID(t, uuid, domain.Account{
			Username:  "SomeGuy",
			UUID:      uuid,
			QueriedAt: now.Add(-time.Hour),
		}, nil)
		handler := makeGetAccountByUUIDHandler(getAccountByUUID)

		req := makeRequest("0123456789ABCDEF0123456789ABCDEF")
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusOK, w.Code)
		body := w.Body.String()
		require.JSONEq(t, successJSON, body)
		parsed := parseResponse(t, body)
		require.NotNil(t, parsed.Success)
		require.True(t, *parsed.Success)
		require.NotNil(t, parsed.UUID)
		require.Equal(t, uuid, *parsed.UUID)
		require.Nil(t, parsed.Cause)
		require.NotNil(t, parsed.Username)
		require.Equal(t, "SomeGuy", *parsed.Username)

		require.True(t, *called)
		require.Equal(t, "application/json", w.Result().Header.Get("Content-Type"))
	})

	t.Run("uuid does not exist", func(t *testing.T) {
		t.Parallel()

		getAccountByUUID, called := makeGetAccountByUUID(t, uuid, domain.Account{}, domain.ErrUsernameNotFound)
		handler := makeGetAccountByUUIDHandler(getAccountByUUID)

		req := makeRequest(uuid)
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusNotFound, w.Code)
		body := w.Body.String()
		parsed := parseResponse(t, body)
		require.NotNil(t, parsed.Success)
		require.False(t, *parsed.Success)
		require.Nil(t, parsed.Username)
		require.NotNil(t, parsed.UUID)
		require.Equal(t, uuid, *parsed.UUID)
		require.NotNil(t, parsed.Cause)
		require.Contains(t, *parsed.Cause, "not found")

		require.True(t, *called)
		require.Equal(t, "application/json", w.Result().Header.Get("Content-Type"))
	})

	t.Run("temporarily unavailable", func(t *testing.T) {
		t.Parallel()

		getAccountByUUID, called := makeGetAccountByUUID(t, uuid, domain.Account{}, domain.ErrTemporarilyUnavailable)
		handler := makeGetAccountByUUIDHandler(getAccountByUUID)

		req := makeRequest(uuid)
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusServiceUnavailable, w.Code)
		body := w.Body.String()
		parsed := parseResponse(t, body)
		require.NotNil(t, parsed.Success)
		require.False(t, *parsed.Success)
		require.Nil(t, parsed.Username)
		require.NotNil(t, parsed.UUID)
		require.Equal(t, uuid, *parsed.UUID)
		require.NotNil(t, parsed.Cause)
		require.Contains(t, *parsed.Cause, "temporarily unavailable")

		require.True(t, *called)
		require.Equal(t, "application/json", w.Result().Header.Get("Content-Type"))
	})

	t.Run("invalid uuid", func(t *testing.T) {
		t.Parallel()

		getAccountByUUID, called := makeGetAccountByUUID(t, uuid, domain.Account{}, domain.ErrTemporarilyUnavailable)
		handler := makeGetAccountByUUIDHandler(getAccountByUUID)

		req := makeRequest("not-a-uuid")
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusBadRequest, w.Code)
		body := w.Body.String()
		parsed := parseResponse(t, body)
		require.NotNil(t, parsed.Success)
		require.False(t, *parsed.Success)
		require.Nil(t, parsed.Username)
		require.NotNil(t, parsed.UUID)
		require.Equal(t, "not-a-uuid", *parsed.UUID)
		require.NotNil(t, parsed.Cause)
		require.Contains(t, *parsed.Cause, "invalid uuid")

		require.False(t, *called)
		require.Equal(t, "application/json", w.Result().Header.Get("Content-Type"))
	})

	t.Run("returns cors headers", func(t *testing.T) {
		t.Parallel()

		getAccountByUUID, called := makeGetAccountByUUID(t, uuid, domain.Account{
			Username:  "SomeGuy",
			UUID:      uuid,
			QueriedAt: now.Add(-time.Hour),
		}, nil)
		handler := makeGetAccountByUUIDHandler(getAccountByUUID)

		origin := "https://subdomain.example.com"

		req := makeRequest(uuid)
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
