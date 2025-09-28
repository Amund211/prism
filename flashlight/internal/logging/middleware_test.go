package logging_test

import (
	"bytes"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"

	"github.com/Amund211/flashlight/internal/logging"
	"github.com/stretchr/testify/require"
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
		require.NoError(t, err)
		attrs := make([]StringAttr, 0)

		foundBase := 0
		for key, value := range logEntry {
			if key == "msg" {
				require.Equal(t, "test", value)
				foundBase++
			} else if key == "level" {
				require.Equal(t, "INFO", value)
				foundBase++
			} else if key == "time" {
				foundBase++
			} else if key == "correlationID" {
				foundBase++
			} else {
				attrs = append(attrs, StringAttr{Key: key, Value: value.(string)})
			}
		}

		require.Equal(t, 4, foundBase)

		return attrs
	}

	t.Run("with middleware", func(t *testing.T) {
		t.Parallel()

		t.Run("all props", func(t *testing.T) {
			t.Parallel()

			requestUrl, err := url.Parse("http://example.com/my-path?uuid=requested-uuid")
			require.NoError(t, err)

			attrs := run(&http.Request{
				URL:    requestUrl,
				Method: "GET",
				Header: http.Header{
					"User-Agent": []string{"user-agent/1.0"},
				},
			}, true)

			require.ElementsMatch(t, []StringAttr{
				{Key: "userAgent", Value: "user-agent/1.0"},
				{Key: "methodPath", Value: "GET /my-path"},
			}, attrs)
		})

		t.Run("bad request", func(t *testing.T) {
			t.Parallel()

			requestUrl, err := url.Parse("http://example.com/my-other-path")
			require.NoError(t, err)

			attrs := run(&http.Request{
				URL:    requestUrl,
				Method: "POST",
			}, true)

			require.ElementsMatch(t, []StringAttr{
				{Key: "userAgent", Value: "<missing>"},
				{Key: "methodPath", Value: "POST /my-other-path"},
			}, attrs)
		})
	})

	t.Run("without middleware", func(t *testing.T) {
		t.Parallel()

		logging.FromContext(t.Context()).Info("don't crash when no logger in context")
	})
}
