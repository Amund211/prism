package ratelimiting

import (
	"context"
	"slices"
	"sync"
	"time"

	"github.com/Amund211/flashlight/internal/logging"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
)

type CancelableRequestLimiter interface {
	LimitCancelable(ctx context.Context, minOperationTime time.Duration, operation func(ctx context.Context) bool) bool
}

type composedRequestLimiter struct {
	limiters []CancelableRequestLimiter
}

func NewComposedRequestLimiter(
	limiters ...CancelableRequestLimiter,
) *composedRequestLimiter {
	return &composedRequestLimiter{
		limiters: limiters,
	}
}

func (l *composedRequestLimiter) Limit(ctx context.Context, minOperationTime time.Duration, operation func(ctx context.Context)) bool {
	limited := func(ctx context.Context) bool {
		operation(ctx)
		return true
	}
	for i := len(l.limiters) - 1; i >= 0; i-- {
		limiter := l.limiters[i]
		prevLimited := limited
		limited = func(ctx context.Context) bool {
			return limiter.LimitCancelable(ctx, minOperationTime, func(ctx context.Context) bool {
				return prevLimited(ctx)
			})
		}
	}
	return limited(ctx)
}

type windowLimitRequestLimiter struct {
	limit     int
	window    time.Duration
	nowFunc   func() time.Time
	afterFunc func(time.Duration) <-chan time.Time

	availableSlots   chan struct{}
	finishedRequests []time.Time
	mutex            sync.Mutex

	tracer trace.Tracer
}

func NewWindowLimitRequestLimiter(
	limit int,
	window time.Duration,
	nowFunc func() time.Time,
	afterFunc func(time.Duration) <-chan time.Time,
) *windowLimitRequestLimiter {
	availableSlots := make(chan struct{}, limit)
	finishedRequests := make([]time.Time, limit)

	// No finished requests within the window -> no waiting for the first requests
	veryOldTime := nowFunc().Add(-window)

	// Initialize the limiter with slots and finished requests outside the window
	for i := range limit {
		finishedRequests[i] = veryOldTime
		availableSlots <- struct{}{}
	}

	return &windowLimitRequestLimiter{
		limit:     limit,
		window:    window,
		nowFunc:   nowFunc,
		afterFunc: afterFunc,

		availableSlots:   availableSlots,
		finishedRequests: finishedRequests,
		mutex:            sync.Mutex{},

		tracer: otel.Tracer("flashlight/ratelimiting"),
	}
}

func insertSortedOrder(arr []time.Time, t time.Time) []time.Time {
	i, _ := slices.BinarySearchFunc(arr, t, func(a, b time.Time) int {
		if a.Before(b) {
			return -1
		}
		if a.After(b) {
			return 1
		}
		return 0
	})
	return slices.Insert(arr, i, t)
}

func (l *windowLimitRequestLimiter) Limit(ctx context.Context, minOperationTime time.Duration, operation func(ctx context.Context)) bool {
	return l.LimitCancelable(ctx, minOperationTime, func(ctx context.Context) bool {
		operation(ctx)
		return true
	})
}

func (l *windowLimitRequestLimiter) LimitCancelable(ctx context.Context, minOperationTime time.Duration, operation func(ctx context.Context) bool) bool {
	return l.waitIf(ctx, func(ctx context.Context, wait time.Duration) bool {
		if wait <= 0 {
			// No wait needed, we can proceed
			// The context may still be about to expire, but we can rather handle that error in the operation
			logging.FromContext(ctx).Info("No wait needed for rate limit, proceeding with operation", "wait", wait)
			return true
		}

		deadline, ok := ctx.Deadline()
		if !ok {
			// No deadline, we can proceed
			logging.FromContext(ctx).Info("No deadline in context, proceeding with operation", "wait", wait)
			return true
		}

		minDuration := wait + minOperationTime
		untilDeadline := deadline.Sub(l.nowFunc())
		if minDuration > untilDeadline {
			// We don't have enough time to wait and then perform the operation - even in the best case
			logging.FromContext(ctx).Info("Not enough time to wait and perform operation within context deadline, aborting", "wait", wait, "minOperationTime", minOperationTime, "untilDeadline", untilDeadline)
			return false
		}

		logging.FromContext(ctx).Info("Enough time to wait and perform operation within context deadline, proceeding", "wait", wait, "minOperationTime", minOperationTime, "untilDeadline", untilDeadline)
		return true
	}, operation)
}

func (l *windowLimitRequestLimiter) waitIf(ctx context.Context, shouldRun func(ctx context.Context, wait time.Duration) bool, operation func(ctx context.Context) bool) bool {
	// Make sure there is data in the request history
	select {
	case <-l.availableSlots:
		// Make sure to return the slot when we are done
		defer func() {
			l.availableSlots <- struct{}{}
		}()
		logging.FromContext(ctx).Info("Acquired available slot for operation")
	case <-ctx.Done():
		logging.FromContext(ctx).Info("Context done while waiting for available slot", "error", ctx.Err())
		return false
	}

	oldestRequest, ok := l.grabOldestFinishedRequest(ctx, shouldRun)
	if !ok {
		logging.FromContext(ctx).Info("Decided not to run operation after checking oldest finished request")
		return false
	}
	// Since we grabbed a request, we need to put one back when we return
	requestToInsert := oldestRequest // If we return without running the operation, we reinsert the request we grabbed
	defer func() {
		l.insertFinishedRequest(requestToInsert)
	}()

	if wait := l.computeWait(oldestRequest); wait > 0 {
		ctx, span := l.tracer.Start(ctx, "windowLimitRequestLimiter.wait")
		logging.FromContext(ctx).Info("Waiting before performing operation", "wait", wait)

		select {
		case <-ctx.Done():
			span.SetStatus(codes.Error, "context done while waiting")
			span.End()
			logging.FromContext(ctx).Info("Context done while waiting", "error", ctx.Err())
			return false
		case <-l.afterFunc(wait):
			span.End()
		}
	}

	// Perform the operation
	ran := operation(ctx)
	if !ran {
		logging.FromContext(ctx).Info("Operation decided not to run")
		return false
	}

	requestToInsert = l.nowFunc()
	logging.FromContext(ctx).Info("Operation completed, recording finished request", "finishedRequestTime", requestToInsert)
	return true
}

func (l *windowLimitRequestLimiter) computeWait(oldRequest time.Time) time.Duration {
	timeSinceRequest := l.nowFunc().Sub(oldRequest)
	remainingTimeInWindow := l.window - timeSinceRequest
	return remainingTimeInWindow
}

func (l *windowLimitRequestLimiter) insertFinishedRequest(finishedRequest time.Time) {
	l.mutex.Lock()
	defer l.mutex.Unlock()
	l.finishedRequests = insertSortedOrder(l.finishedRequests, finishedRequest)
}

func (l *windowLimitRequestLimiter) grabOldestFinishedRequest(ctx context.Context, shouldRun func(context.Context, time.Duration) bool) (time.Time, bool) {
	l.mutex.Lock()
	defer l.mutex.Unlock()

	oldestRequest := l.finishedRequests[0]
	wait := l.computeWait(oldestRequest)
	run := shouldRun(ctx, wait)
	if !run {
		return time.Time{}, false
	}

	// Remove and return the oldest request
	l.finishedRequests = l.finishedRequests[1:]
	return oldestRequest, true
}
