package ratelimiting

import (
	"context"
	"slices"
	"sync"
	"time"
)

type CancelableRequestLimiter interface {
	LimitCancelable(ctx context.Context, minOperationTime time.Duration, operation func() bool) bool
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

func (l *composedRequestLimiter) Limit(ctx context.Context, minOperationTime time.Duration, operation func()) bool {
	limited := func() bool {
		operation()
		return true
	}
	for i := len(l.limiters) - 1; i >= 0; i-- {
		limiter := l.limiters[i]
		prevLimited := limited
		limited = func() bool {
			return limiter.LimitCancelable(ctx, minOperationTime, func() bool {
				return prevLimited()
			})
		}
	}
	return limited()
}

type windowLimitRequestLimiter struct {
	limit     int
	window    time.Duration
	nowFunc   func() time.Time
	afterFunc func(time.Duration) <-chan time.Time

	availableSlots   chan struct{}
	finishedRequests []time.Time
	mutex            sync.Mutex
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

func (l *windowLimitRequestLimiter) Limit(ctx context.Context, minOperationTime time.Duration, operation func()) bool {
	return l.LimitCancelable(ctx, minOperationTime, func() bool {
		operation()
		return true
	})
}

func (l *windowLimitRequestLimiter) LimitCancelable(ctx context.Context, minOperationTime time.Duration, operation func() bool) bool {
	return l.waitIf(ctx, func(ctx context.Context, wait time.Duration) bool {
		if wait <= 0 {
			// No wait needed, we can proceed
			// The context may still be about to expire, but we can rather handle that error in the operation
			return true
		}

		deadline, ok := ctx.Deadline()
		if !ok {
			// No deadline, we can proceed
			return true
		}

		minDuration := wait + minOperationTime
		untilDeadline := deadline.Sub(l.nowFunc())
		if minDuration > untilDeadline {
			// We don't have enough time to wait and then perform the operation - even in the best case
			return false
		}

		return true
	}, operation)
}

func (l *windowLimitRequestLimiter) waitIf(ctx context.Context, shouldRun func(ctx context.Context, wait time.Duration) bool, operation func() bool) bool {
	// Make sure there is data in the request history
	select {
	case <-l.availableSlots:
		// Make sure to return the slot when we are done
		defer func() {
			l.availableSlots <- struct{}{}
		}()
	case <-ctx.Done():
		return false
	}

	oldestRequest, ok := l.grabOldestFinishedRequest(ctx, shouldRun)
	if !ok {
		return false
	}
	// Since we grabbed a request, we need to put one back when we return
	requestToInsert := oldestRequest // If we return without running the operation, we reinsert the request we grabbed
	defer func() {
		l.insertFinishedRequest(requestToInsert)
	}()

	if wait := l.computeWait(oldestRequest); wait > 0 {
		select {
		case <-ctx.Done():
			return false
		case <-l.afterFunc(wait):
		}
	}

	// Perform the operation
	ran := operation()
	if !ran {
		return false
	}

	requestToInsert = l.nowFunc()
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
