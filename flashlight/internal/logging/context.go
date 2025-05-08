package logging

import (
	"context"
	"log/slog"
	"os"
)

type requestLoggerContextKey struct{}

func FromContext(ctx context.Context) *slog.Logger {
	logger, ok := ctx.Value(requestLoggerContextKey{}).(*slog.Logger)
	if !ok || logger == nil {
		fallback := slog.New(slog.NewJSONHandler(os.Stdout, nil))
		fallback = fallback.With(slog.String("logger", "fallback"))
		return fallback
	}
	return logger
}

func AddToContext(ctx context.Context, logger *slog.Logger) context.Context {
	return context.WithValue(ctx, requestLoggerContextKey{}, logger)
}

func AddMetaToContext(ctx context.Context, args ...slog.Attr) context.Context {
	logger := FromContext(ctx)

	// Convert our []slog.Attr to []any
	anySlice := make([]any, len(args))
	for i, arg := range args {
		anySlice[i] = arg
	}

	withMeta := logger.With(anySlice...)

	return AddToContext(ctx, withMeta)
}
