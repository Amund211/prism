package reporting

import (
	"context"
	"maps"
	"time"
)

type reportingMetaContextKey struct{}

type ReportingMeta struct {
	tags      map[string]string
	extras    map[string]string
	userID    string
	startedAt time.Time
}

func MetaFromContext(ctx context.Context) ReportingMeta {
	meta, ok := ctx.Value(reportingMetaContextKey{}).(ReportingMeta)
	if !ok {
		return ReportingMeta{
			tags:      make(map[string]string),
			extras:    make(map[string]string),
			userID:    "",
			startedAt: time.Time{},
		}
	}
	return ReportingMeta{
		tags:      maps.Clone(meta.tags),
		extras:    maps.Clone(meta.extras),
		userID:    meta.userID,
		startedAt: meta.startedAt,
	}
}

func addMetaToContext(ctx context.Context, meta ReportingMeta) context.Context {
	return context.WithValue(ctx, reportingMetaContextKey{}, meta)
}

func setStartedAtInContext(ctx context.Context, startedAt time.Time) context.Context {
	meta := MetaFromContext(ctx)
	meta.startedAt = startedAt

	return addMetaToContext(ctx, meta)
}

func AddExtrasToContext(ctx context.Context, extras map[string]string) context.Context {
	meta := MetaFromContext(ctx)

	for key, value := range extras {
		meta.extras[key] = value
	}

	return addMetaToContext(ctx, meta)
}

func AddTagsToContext(ctx context.Context, tags map[string]string) context.Context {
	meta := MetaFromContext(ctx)

	for key, value := range tags {
		meta.tags[key] = value
	}

	return addMetaToContext(ctx, meta)
}

func SetUserIDInContext(ctx context.Context, userID string) context.Context {
	meta := MetaFromContext(ctx)
	meta.userID = userID

	return addMetaToContext(ctx, meta)
}
