package logging_test

import (
	"bytes"
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"

	"github.com/Amund211/flashlight/internal/logging"
	"github.com/stretchr/testify/assert"
)

type StringAttr struct {
	Key   string
	Value string
}

func TestRequestLoggerMiddleware(t *testing.T) {
	run := func(request *http.Request, useMiddleware bool) []StringAttr {
		t.Helper()

		buf := &bytes.Buffer{}
		middleware := logging.NewRequestLoggerMiddleware(slog.New(slog.NewJSONHandler(buf, nil)))

		logRequest := func(w http.ResponseWriter, r *http.Request) {
			logging.FromContext(r.Context()).Info("test")
		}

		handler := logRequest
		if useMiddleware {
			handler = middleware(logRequest)
		}

		w := httptest.NewRecorder()
		handler(w, request)

		var logEntry map[string]interface{}
		err := json.Unmarshal(buf.Bytes(), &logEntry)
		assert.NoError(t, err)
		attrs := make([]StringAttr, 0)

		foundBase := 0
		for key, value := range logEntry {
			if key == "msg" {
				assert.Equal(t, "test", value)
				foundBase++
			} else if key == "level" {
				assert.Equal(t, "INFO", value)
				foundBase++
			} else if key == "time" {
				foundBase++
			} else if key == "correlationID" {
				foundBase++
			} else {
				attrs = append(attrs, StringAttr{Key: key, Value: value.(string)})
			}
		}

		assert.Equal(t, 4, foundBase)

		return attrs
	}

	t.Run("with middleware", func(t *testing.T) {
		t.Run("all props", func(t *testing.T) {
			requestUrl, err := url.Parse("http://example.com/my-path?uuid=requested-uuid")
			assert.NoError(t, err)

			attrs := run(&http.Request{
				URL:    requestUrl,
				Method: "GET",
				Header: http.Header{
					"X-User-Id":  []string{"user-id"},
					"User-Agent": []string{"user-agent/1.0"},
				},
			}, true)

			assert.ElementsMatch(t, []StringAttr{
				{Key: "uuid", Value: "requested-uuid"},
				{Key: "userId", Value: "user-id"},
				{Key: "userAgent", Value: "user-agent/1.0"},
				{Key: "methodPath", Value: "GET /my-path"},
			}, attrs)
		})

		t.Run("bad request", func(t *testing.T) {
			requestUrl, err := url.Parse("http://example.com/my-other-path")
			assert.NoError(t, err)

			attrs := run(&http.Request{
				URL:    requestUrl,
				Method: "POST",
			}, true)

			assert.ElementsMatch(t, []StringAttr{
				{Key: "uuid", Value: "<missing>"},
				{Key: "userId", Value: "<missing>"},
				{Key: "userAgent", Value: "<missing>"},
				{Key: "methodPath", Value: "POST /my-other-path"},
			}, attrs)
		})
	})

	t.Run("without middleware", func(t *testing.T) {
		logging.FromContext(context.Background()).Info("don't crash when no logger in context")
	})
}
