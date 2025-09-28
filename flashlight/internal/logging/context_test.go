package logging_test

import (
	"bytes"
	"encoding/json"
	"log/slog"
	"testing"
	"time"

	"github.com/Amund211/flashlight/internal/logging"
	"github.com/stretchr/testify/require"
)

func newWriter(t *testing.T) *jsonWriter {
	return &jsonWriter{
		t:    t,
		data: make([]string, 0),
	}
}

type jsonWriter struct {
	t    *testing.T
	data []string
}

func (w *jsonWriter) Write(p []byte) (int, error) {
	w.t.Helper()
	w.data = append(w.data, string(p))
	return len(p), nil
}

func (w *jsonWriter) PopWithoutTime() (map[string]any, bool) {
	w.t.Helper()
	if len(w.data) == 0 {
		return nil, false
	}

	lastIndex := len(w.data) - 1
	val := w.data[lastIndex]
	w.data = w.data[:lastIndex]

	var result map[string]any
	err := json.Unmarshal([]byte(val), &result)
	require.NoError(w.t, err)

	timeValue, ok := result["time"]
	require.True(w.t, ok)

	timeStr, ok := timeValue.(string)
	require.True(w.t, ok)

	timeTime, err := time.Parse(time.RFC3339, timeStr)
	require.NoError(w.t, err)

	require.WithinDuration(w.t, time.Now(), timeTime, 5*time.Second)

	// Drop "time" as it is hard to match against
	delete(result, "time")

	return result, true
}

func (w *jsonWriter) RequireEmpty() {
	w.t.Helper()
	require.Empty(w.t, w.data)
}

func TestFromContext(t *testing.T) {
	t.Parallel()

	ctx := t.Context()
	buf := &bytes.Buffer{}
	logger := slog.New(slog.NewJSONHandler(buf, nil))
	ctx = logging.AddToContext(ctx, logger)

	retrievedLogger := logging.FromContext(ctx)
	require.Equal(t, logger, retrievedLogger)
}

func TestAddMetaToContext(t *testing.T) {
	t.Parallel()

	ctx := t.Context()
	w := newWriter(t)
	rootLogger := slog.New(slog.NewJSONHandler(w, nil)).With(slog.String("rootprop", "rootval"))
	ctx = logging.AddToContext(ctx, rootLogger)

	w.RequireEmpty()

	rootLogger.Info("test")

	entry, ok := w.PopWithoutTime()
	require.True(t, ok)

	require.Equal(t, map[string]any{
		"level":    "INFO",
		"msg":      "test",
		"rootprop": "rootval",
	}, entry)

	w.RequireEmpty()

	ctx = logging.AddMetaToContext(ctx, slog.String("testprop", "testval"))
	l1Logger := logging.FromContext(ctx)
	l1Logger.Info("test")
	entry, ok = w.PopWithoutTime()
	require.True(t, ok)
	require.Equal(t, map[string]any{
		"level":    "INFO",
		"msg":      "test",
		"rootprop": "rootval",
		"testprop": "testval",
	}, entry)
	w.RequireEmpty()

	ctx = logging.AddMetaToContext(ctx, slog.String("testprop", "testval2"), slog.String("rootprop", "rootval2"))
	l2Logger := logging.FromContext(ctx)
	l2Logger.Info("test")
	entry, ok = w.PopWithoutTime()
	require.True(t, ok)
	require.Equal(t, map[string]any{
		"level":    "INFO",
		"msg":      "test",
		"rootprop": "rootval2",
		"testprop": "testval2",
	}, entry)
}
