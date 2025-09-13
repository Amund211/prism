package ratelimiting

import (
	"context"
	"slices"
	"sync"
	"time"
)

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
	for i := 0; i < limit; i++ {
		availableSlots <- struct{}{}
	}

	// No finished requests within the window -> no waiting for the first requests
	finishedRequests := make([]time.Time, limit)
	veryOldTime := nowFunc().Add(-window)
	for i := 0; i < limit; i++ {
		finishedRequests[i] = veryOldTime
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

func (l *windowLimitRequestLimiter) Limit(ctx context.Context, maxOperationTime time.Duration, operation func()) bool {
	return l.LimitCancelable(ctx, maxOperationTime, func() bool {
		operation()
		return true
	})
}

func (l *windowLimitRequestLimiter) LimitCancelable(ctx context.Context, maxOperationTime time.Duration, operation func() bool) bool {
	return l.waitIf(ctx, func(ctx context.Context, wait time.Duration) bool {
		deadline, ok := ctx.Deadline()
		if !ok {
			// No deadline, we can proceed
			return true
		}

		maxDuration := wait + maxOperationTime
		untilDeadline := deadline.Sub(l.nowFunc())
		if maxDuration > untilDeadline {
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
