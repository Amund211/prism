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
	"github.com/Amund211/flashlight/internal/domaintest"
	"github.com/Amund211/flashlight/internal/ports"
	"github.com/stretchr/testify/require"
)

func TestMakeGetTagsHandler(t *testing.T) {
	t.Parallel()

	testLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	noopMiddleware := func(h http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			h(w, r)
		}
	}

	makeGetTags := func(t *testing.T, expectedUUID string, tags domain.Tags, err error) (app.GetTags, *bool) {
		called := false
		return func(ctx context.Context, uuid string, apiKey *string) (domain.Tags, error) {
			t.Helper()
			require.Equal(t, expectedUUID, uuid)
			require.Nil(t, apiKey)

			called = true

			return tags, err
		}, &called
	}

	makeGetTagsHandler := func(getTags app.GetTags) http.HandlerFunc {
		stubRegisterUserVisit := func(ctx context.Context, userID string) (domain.User, error) {
			return domain.User{}, nil
		}
		return ports.MakeGetTagsHandler(
			getTags,
			stubRegisterUserVisit,
			testLogger,
			noopMiddleware,
		)
	}

	uuid := "01234567-89ab-cdef-0123-456789abcdef"

	makeRequest := func(uuid string) *http.Request {
		req := httptest.NewRequest("GET", "/v1/tags/"+uuid, nil)
		req.SetPathValue("uuid", uuid)
		return req
	}

	t.Run("successful tags retrieval with none severity", func(t *testing.T) {
		t.Parallel()

		tags := domain.Tags{
			Cheating: domain.TagSeverityNone,
			Sniping:  domain.TagSeverityNone,
		}

		getTagsFunc, called := makeGetTags(t, uuid, tags, nil)
		handler := makeGetTagsHandler(getTagsFunc)

		req := makeRequest(uuid)
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusOK, w.Code)
		require.JSONEq(t, fmt.Sprintf(`{"uuid":"%s","tags":{"cheating":"none","sniping":"none"}}`, uuid), w.Body.String())
		require.True(t, *called)
		require.Equal(t, "application/json", w.Result().Header.Get("Content-Type"))
	})

	t.Run("successful tags retrieval with medium severity", func(t *testing.T) {
		t.Parallel()

		tags := domain.Tags{
			Cheating: domain.TagSeverityMedium,
			Sniping:  domain.TagSeverityNone,
		}

		getTagsFunc, called := makeGetTags(t, uuid, tags, nil)
		handler := makeGetTagsHandler(getTagsFunc)

		req := makeRequest(uuid)
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusOK, w.Code)
		require.JSONEq(t, fmt.Sprintf(`{"uuid":"%s","tags":{"cheating":"medium","sniping":"none"}}`, uuid), w.Body.String())
		require.True(t, *called)
		require.Equal(t, "application/json", w.Result().Header.Get("Content-Type"))
	})

	t.Run("successful tags retrieval with high severity", func(t *testing.T) {
		t.Parallel()

		tags := domain.Tags{
			Cheating: domain.TagSeverityHigh,
			Sniping:  domain.TagSeverityHigh,
		}

		getTagsFunc, called := makeGetTags(t, uuid, tags, nil)
		handler := makeGetTagsHandler(getTagsFunc)

		req := makeRequest(uuid)
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusOK, w.Code)
		require.JSONEq(t, fmt.Sprintf(`{"uuid":"%s","tags":{"cheating":"high","sniping":"high"}}`, uuid), w.Body.String())
		require.True(t, *called)
		require.Equal(t, "application/json", w.Result().Header.Get("Content-Type"))
	})

	t.Run("urchin api key is passed through", func(t *testing.T) {
		t.Parallel()

		expectedUUID := domaintest.NewUUID(t)

		urchinAPIKey := domaintest.NewUUID(t)

		tags := domain.Tags{
			Cheating: domain.TagSeverityMedium,
			Sniping:  domain.TagSeverityHigh,
		}

		called := false
		getTags := func(ctx context.Context, uuid string, apiKey *string) (domain.Tags, error) {
			t.Helper()
			require.Equal(t, expectedUUID, uuid)
			require.NotNil(t, apiKey)
			require.Equal(t, urchinAPIKey, *apiKey)

			called = true

			return tags, nil
		}

		handler := makeGetTagsHandler(getTags)

		req := makeRequest(expectedUUID)
		req.Header.Set("X-Urchin-Api-Key", urchinAPIKey)
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusOK, w.Code)
		require.JSONEq(t, fmt.Sprintf(`{"uuid":"%s","tags":{"cheating":"medium","sniping":"high"}}`, expectedUUID), w.Body.String())
		require.True(t, called)
		require.Equal(t, "application/json", w.Result().Header.Get("Content-Type"))
	})

	t.Run("uuid is normalized", func(t *testing.T) {
		t.Parallel()

		tags := domain.Tags{
			Cheating: domain.TagSeverityNone,
			Sniping:  domain.TagSeverityNone,
		}

		getTagsFunc, called := makeGetTags(t, uuid, tags, nil)
		handler := makeGetTagsHandler(getTagsFunc)

		req := makeRequest("0123456789ABCDEF0123456789ABCDEF")
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusOK, w.Code)
		require.JSONEq(t, fmt.Sprintf(`{"uuid":"%s","tags":{"cheating":"none","sniping":"none"}}`, uuid), w.Body.String())
		require.True(t, *called)
		require.Equal(t, "application/json", w.Result().Header.Get("Content-Type"))
	})

	t.Run("invalid uuid", func(t *testing.T) {
		t.Parallel()

		tags := domain.Tags{}

		getTagsFunc, called := makeGetTags(t, uuid, tags, nil)
		handler := makeGetTagsHandler(getTagsFunc)

		req := makeRequest("not-a-uuid")
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusBadRequest, w.Code)
		require.Contains(t, w.Body.String(), "Invalid uuid")
		require.False(t, *called)
	})

	t.Run("temporarily unavailable", func(t *testing.T) {
		t.Parallel()

		getTagsFunc, called := makeGetTags(t, uuid, domain.Tags{}, domain.ErrTemporarilyUnavailable)
		handler := makeGetTagsHandler(getTagsFunc)

		req := makeRequest(uuid)
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusServiceUnavailable, w.Code)
		require.Contains(t, w.Body.String(), "Temporarily unavailable")
		require.True(t, *called)
	})

	t.Run("internal server error", func(t *testing.T) {
		t.Parallel()

		getTagsFunc, called := makeGetTags(t, uuid, domain.Tags{}, fmt.Errorf("some error"))
		handler := makeGetTagsHandler(getTagsFunc)

		req := makeRequest(uuid)
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusInternalServerError, w.Code)
		require.Contains(t, w.Body.String(), "Internal server error")
		require.True(t, *called)
	})

	t.Run("invalid api key", func(t *testing.T) {
		t.Parallel()

		getTagsFunc, called := makeGetTags(t, uuid, domain.Tags{}, domain.ErrInvalidAPIKey)
		handler := makeGetTagsHandler(getTagsFunc)

		req := makeRequest(uuid)
		w := httptest.NewRecorder()

		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusUnauthorized, w.Code)
		require.Contains(t, w.Body.String(), "Invalid urchin API key. Fix it or remove the key.")
		require.True(t, *called)
	})
}
