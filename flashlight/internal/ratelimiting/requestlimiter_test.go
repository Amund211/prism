package ratelimiting_test

import (
	"context"
	"fmt"
	"runtime"
	"slices"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type mockedTime struct {
	t           *testing.T
	currentTime time.Time
	timers      []mockedTimer
	lock        sync.Mutex
}

type mockedTimer struct {
	expiresAt time.Time
	ch        chan<- time.Time
}

func newMockedTime(t *testing.T, start time.Time) *mockedTime {
	return &mockedTime{
		t:           t,
		currentTime: start,
		timers:      []mockedTimer{},
		lock:        sync.Mutex{},
	}
}

func (m *mockedTime) Now() time.Time {
	m.t.Helper()

	return m.currentTime
}

func (m *mockedTime) After(d time.Duration) <-chan time.Time {
	m.t.Helper()

	m.lock.Lock()
	defer m.lock.Unlock()

	ch := make(chan time.Time, 1)
	m.timers = append(m.timers, mockedTimer{
		ch:        ch,
		expiresAt: m.currentTime.Add(d),
	})

	return ch
}

func (m *mockedTime) advance(d time.Duration) {
	m.t.Helper()

	m.lock.Lock()
	defer m.lock.Unlock()

	m.currentTime = m.currentTime.Add(d)

	var remainingTimers []mockedTimer
	for _, timer := range m.timers {
		if !m.currentTime.Before(timer.expiresAt) {
			// Timer has expired, send the time
			timer.ch <- m.currentTime
			close(timer.ch)
		} else {
			remainingTimers = append(remainingTimers, timer)
		}
	}
	m.timers = remainingTimers
}

func (m *mockedTime) sleep(d time.Duration) {
	m.t.Helper()
	if d <= 0 {
		return
	}

	select {
	case <-m.After(d):
		return
	case <-time.After(5 * time.Second):
		require.False(m.t, true, "sleep timed out")
	}
}

type mockedContext struct {
	deadline time.Time
	done     chan struct{}
}

func newMockedContext(deadline time.Time) (*mockedContext, func()) {
	done := make(chan struct{})
	return &mockedContext{
			deadline: deadline,
			done:     done,
		}, func() {
			close(done)
		}
}

func (m *mockedContext) Deadline() (deadline time.Time, ok bool) {
	return m.deadline, !m.deadline.IsZero()
}

func (m *mockedContext) Done() <-chan struct{} {
	return m.done
}

func (m *mockedContext) Err() error {
	panic("not implemented")
}

func (m *mockedContext) Value(key any) any {
	panic("not implemented")
}

func TestWindowLimitRequestLimiter(t *testing.T) {
	t.Parallel()
	ctx := context.Background()

	t.Run("init", func(t *testing.T) {
		t.Parallel()
		l := ratelimiting.NewWindowLimitRequestLimiter(5, 10*time.Minute, time.Now, time.After)
		require.NotNil(t, l)
	})

	t.Run("limiters don't share state", func(t *testing.T) {
		t.Parallel()
		l1 := ratelimiting.NewWindowLimitRequestLimiter(1, 1*time.Hour, time.Now, time.After)
		l2 := ratelimiting.NewWindowLimitRequestLimiter(1, 1*time.Hour, time.Now, time.After)
		l3 := ratelimiting.NewWindowLimitRequestLimiter(1, 1*time.Hour, time.Now, time.After)
		l4 := ratelimiting.NewWindowLimitRequestLimiter(1, 1*time.Hour, time.Now, time.After)
		require.True(t, l1.Limit(ctx, 1*time.Second, func() {}))
		require.True(t, l2.Limit(ctx, 1*time.Second, func() {}))
		require.True(t, l3.Limit(ctx, 1*time.Second, func() {}))
		require.True(t, l4.Limit(ctx, 1*time.Second, func() {}))
	})

	t.Run("concurrent requests > limit", func(t *testing.T) {
		t.Parallel()
		start := time.Date(2024, time.January, 1, 0, 0, 0, 0, time.UTC)
		mocked := newMockedTime(t, start)
		l := ratelimiting.NewWindowLimitRequestLimiter(2, 10*time.Second, mocked.Now, mocked.After)
		minOperationTime := 500 * time.Millisecond // Doesn't matter since we don't have a deadline
		operationTime := 1 * time.Second

		requests := 100
		mutex := sync.Mutex{}
		startedAt := make([]time.Time, 0)
		completedRequests := atomic.Int32{}

		issueRequest := func() {
			t.Helper()

			go func() {
				t.Helper()
				defer completedRequests.Add(1)

				ran := l.Limit(ctx, minOperationTime, func() {
					t.Helper()

					mutex.Lock()
					startedAt = append(startedAt, mocked.Now())
					mutex.Unlock()

					mocked.sleep(operationTime)
				})
				require.True(t, ran)
			}()
		}

		// These requests should start immediately
		for i := 0; i < requests; i++ {
			issueRequest()
		}

		for completedRequests.Load() < int32(requests) {
			mocked.advance(1 * time.Second)
			for i := 0; i < requests; i++ {
				runtime.Gosched() // Allow other goroutines to run
			}
		}

		slices.SortFunc(startedAt, func(a, b time.Time) int {
			if a.Before(b) {
				return -1
			} else if a.After(b) {
				return 1
			}
			return 0
		})

		require.Len(t, startedAt, requests)
		for i := 0; i < requests; i++ {
			batch := i / 2
			waitPerBatch := 10*time.Second + 1*time.Second
			earliestStart := start.Add(time.Duration(batch) * waitPerBatch)
			require.GreaterOrEqual(t, startedAt[i], earliestStart)
		}
	})

	t.Run("request with high timeout waits", func(t *testing.T) {
		t.Parallel()
		start := time.Date(2024, time.January, 1, 0, 0, 0, 0, time.UTC)
		for _, timeout := range []time.Duration{
			12*time.Second + 1*time.Millisecond,
			15 * time.Second,
			20 * time.Second,
			25 * time.Second,
			30 * time.Second,
			60 * time.Second,
		} {
			t.Run(timeout.String(), func(t *testing.T) {
				t.Parallel()
				mocked := newMockedTime(t, start)
				l := ratelimiting.NewWindowLimitRequestLimiter(2, 10*time.Second, mocked.Now, mocked.After)
				minOperationTime := 2 * time.Second

				wg := sync.WaitGroup{}
				wg.Add(1)

				// Exhaust the limiter
				ran := l.Limit(ctx, minOperationTime, func() {})
				require.True(t, ran)
				ran = l.Limit(ctx, minOperationTime, func() {})
				require.True(t, ran)

				go func() {
					t.Helper()
					defer wg.Done()

					ctx, close := newMockedContext(start.Add(timeout))
					defer close()

					ran := l.Limit(ctx, minOperationTime, func() {
						t.Helper()
						require.Equal(t, start.Add(10*time.Second), mocked.Now())
					})
					require.True(t, ran)
				}()
				time.Sleep(100 * time.Millisecond) // Give the goroutine time to run and start waiting

				for seconds := 0; seconds < 10; seconds++ {
					runtime.Gosched() // Allow other goroutines to run
					mocked.advance(1 * time.Second)
				}
				wg.Wait()
			})
		}
	})

	t.Run("request always runs when there is no wait", func(t *testing.T) {
		// The limiter should not stop any operations from running if there is no wait
		// This applies even if the context deadline is shorter than the max operation time
		t.Parallel()
		start := time.Date(2024, time.January, 1, 0, 0, 0, 0, time.UTC)
		for _, timeout := range []time.Duration{
			1 * time.Millisecond,
			100 * time.Millisecond,
			200 * time.Millisecond,
			500 * time.Millisecond,
			1 * time.Second,
			2 * time.Second,
			5 * time.Second,
			10 * time.Second,
		} {
			t.Run(timeout.String(), func(t *testing.T) {
				t.Parallel()
				mocked := newMockedTime(t, start)
				l := ratelimiting.NewWindowLimitRequestLimiter(2, 10*time.Second, mocked.Now, mocked.After)
				minOperationTime := 2 * time.Second

				// Exhaust the limiter

				ctx, close := newMockedContext(start.Add(timeout))
				defer close()
				ran := l.Limit(ctx, minOperationTime, func() {})
				require.True(t, ran)
			})
		}
	})

	t.Run("request with low timeout returns early with error", func(t *testing.T) {
		t.Parallel()

		start := time.Date(2024, time.January, 1, 0, 0, 0, 0, time.UTC)

		mockedNow := func() time.Time {
			return start
		}

		for _, timeout := range []time.Duration{
			1 * time.Second,
			2 * time.Second,
			3 * time.Second,
			4 * time.Second,
			5 * time.Second,
			6 * time.Second,
			7 * time.Second,
			8 * time.Second,
			9 * time.Second,
			10 * time.Second,
			11 * time.Second,
			11*time.Second + 999*time.Millisecond,
		} {
			t.Run(timeout.String(), func(t *testing.T) {
				t.Parallel()

				mockedAfter := func(d time.Duration) <-chan time.Time {
					t.Helper()
					require.False(t, true, "After should not be called in this test")
					return nil
				}

				l := ratelimiting.NewWindowLimitRequestLimiter(2, 10*time.Second, mockedNow, mockedAfter)
				minOperationTime := 2 * time.Second

				// Exhaust the limiter
				ran := l.Limit(ctx, minOperationTime, func() {})
				require.True(t, ran)
				ran = l.Limit(ctx, minOperationTime, func() {})
				require.True(t, ran)

				ctx, close := newMockedContext(start.Add(timeout))
				defer close()

				ran = l.Limit(ctx, minOperationTime, func() {
					t.Helper()
					require.Fail(t, "operation should not be called")
				})
				require.False(t, ran)
			})
		}
	})

	t.Run("cancelling requests works", func(t *testing.T) {
		t.Parallel()

		start := time.Date(2024, time.January, 1, 0, 0, 0, 0, time.UTC)
		minOperationTime := 500 * time.Millisecond // Doesn't matter since we don't have a deadline

		afterChan := make(chan time.Time)
		t.Cleanup(func() {
			close(afterChan)
		})

		mockedAfter := func(d time.Duration) <-chan time.Time {
			return afterChan
		}
		mockedNow := func() time.Time {
			return start
		}

		t.Run("canceled requests return from waiting for a slot", func(t *testing.T) {
			t.Parallel()

			requestsStartedWg := sync.WaitGroup{}
			requestsStartedWg.Add(2)

			requestsCompletedWg := sync.WaitGroup{}
			requestsCompletedWg.Add(2)

			requestsWg := sync.WaitGroup{}
			requestsWg.Add(1)

			l := ratelimiting.NewWindowLimitRequestLimiter(2, 10*time.Second, mockedNow, mockedAfter)
			// Consume all concurrency from the limiter
			go func() {
				defer requestsCompletedWg.Done()
				ran := l.Limit(ctx, minOperationTime, func() {
					requestsStartedWg.Done()
					requestsWg.Wait()
				})
				require.True(t, ran)
			}()
			go func() {
				defer requestsCompletedWg.Done()
				ran := l.Limit(ctx, minOperationTime, func() {
					requestsStartedWg.Done()
					requestsWg.Wait()
				})
				require.True(t, ran)
			}()

			// Wait for the requests to start and occupy all slots
			requestsStartedWg.Wait()

			ctx, cancel := context.WithCancel(context.Background())
			cancel() // Cancel immediately

			ran := l.Limit(ctx, minOperationTime, func() {
				t.Helper()
				assert.False(t, true, "operation should not be called")
			})
			require.False(t, ran)

			// Let the other requests finish
			requestsWg.Done()
			requestsCompletedWg.Wait()
		})

		t.Run("canceled requests return from sleep", func(t *testing.T) {
			t.Parallel()

			afterCalled := false
			mockedAfter := func(d time.Duration) <-chan time.Time {
				afterCalled = true
				return afterChan
			}

			l := ratelimiting.NewWindowLimitRequestLimiter(2, 10*time.Second, mockedNow, mockedAfter)
			// Exhaust the limiter
			ran := l.Limit(ctx, minOperationTime, func() {})
			require.True(t, ran)
			ran = l.Limit(ctx, minOperationTime, func() {})
			require.True(t, ran)

			ctx, cancel := context.WithCancel(context.Background())

			limitReturned := false

			go func() {
				ran := l.Limit(ctx, minOperationTime, func() {
					t.Helper()
					assert.False(t, true, "operation should not be called")
				})
				limitReturned = true
				require.False(t, ran)
			}()

			for !afterCalled {
				runtime.Gosched() // Allow other goroutines to run
			}

			time.Sleep(100 * time.Millisecond) // Give the goroutine time to run in case something is wrong

			require.False(t, limitReturned)

			cancel()

			for !limitReturned {
				runtime.Gosched() // Allow other goroutines to run
			}
		})

		t.Run("cancelling requests when acquiring a slot does not affect further requests", func(t *testing.T) {
			t.Parallel()

			now := time.Date(2024, time.January, 1, 0, 0, 0, 0, time.UTC)

			mockedNow := func() time.Time {
				return now
			}

			requestsStartedWg := sync.WaitGroup{}
			requestsStartedWg.Add(2)

			requestsCompletedWg := sync.WaitGroup{}
			requestsCompletedWg.Add(2)

			requestsWg := sync.WaitGroup{}
			requestsWg.Add(1)

			l := ratelimiting.NewWindowLimitRequestLimiter(2, 10*time.Second, mockedNow, mockedAfter)
			// Consume all concurrency from the limiter
			go func() {
				defer requestsCompletedWg.Done()
				ran := l.Limit(ctx, minOperationTime, func() {
					requestsStartedWg.Done()
					requestsWg.Wait()
				})
				require.True(t, ran)
			}()
			go func() {
				defer requestsCompletedWg.Done()
				ran := l.Limit(ctx, minOperationTime, func() {
					requestsStartedWg.Done()
					requestsWg.Wait()
				})
				require.True(t, ran)
			}()

			// Wait for the requests to start and occupy all slots
			requestsStartedWg.Wait()

			ctx, cancel := context.WithCancel(context.Background())
			cancel() // Cancel immediately

			for i := 0; i < 100; i++ {
				ran := l.Limit(ctx, minOperationTime, func() {
					t.Helper()
					assert.False(t, true, "operation should not be called")
				})
				require.False(t, ran)
			}

			// Let the other requests finish
			requestsWg.Done()
			requestsCompletedWg.Wait()

		})

		t.Run("cancelling requests during sleep does not affect further requests", func(t *testing.T) {
			// A sleeping request has grabbed a slot. Cancelling it should put the slot back
			t.Parallel()

			now := time.Date(2024, time.January, 1, 0, 0, 0, 0, time.UTC)

			mockedNow := func() time.Time {
				return now
			}

			afterCalled := false
			mockedAfter := func(d time.Duration) <-chan time.Time {
				afterCalled = true
				return afterChan
			}

			l := ratelimiting.NewWindowLimitRequestLimiter(1, 10*time.Second, mockedNow, mockedAfter)

			// Exhaust the limiter
			ran := l.Limit(ctx, minOperationTime, func() {})
			require.True(t, ran)

			ctxWithCancel, cancel := context.WithCancel(context.Background())
			limitReturned := false
			go func() {
				ran := l.Limit(ctxWithCancel, minOperationTime, func() {
					t.Helper()
					assert.False(t, true, "operation should not be called")
				})
				limitReturned = true
				require.False(t, ran)
			}()

			for !afterCalled {
				runtime.Gosched() // Allow other goroutines to run
			}
			require.False(t, limitReturned)

			now = now.Add(10 * time.Second) // Move time forward to simulate the passage of time between the call and the context being canceled

			cancel()

			for !limitReturned {
				runtime.Gosched() // Allow other goroutines to run
			}

			// Since the request was canceled, and the original request is barely outside the window, this request should be able to proceed
			afterCalled = false

			ran = l.Limit(ctx, minOperationTime, func() {})
			require.True(t, ran)

			require.False(t, afterCalled)
		})

		t.Run("canceling an operation does not affect further requests", func(t *testing.T) {
			t.Parallel()

			now := time.Date(2024, time.January, 1, 0, 0, 0, 0, time.UTC)

			mockedNow := func() time.Time {
				return now
			}

			mockedAfter := func(d time.Duration) <-chan time.Time {
				require.False(t, true, "After should not be called in this test")
				return afterChan
			}

			l := ratelimiting.NewWindowLimitRequestLimiter(2, 10*time.Second, mockedNow, mockedAfter)

			// Exhaust the limiter
			ran := l.Limit(ctx, minOperationTime, func() {})
			require.True(t, ran)
			ran = l.Limit(ctx, minOperationTime, func() {})
			require.True(t, ran)

			// Move both requests just outside the window
			now = now.Add(10 * time.Second)

			ran = l.LimitCancelable(ctx, minOperationTime, func() bool {
				return false // Cancel the operation
			})
			require.False(t, ran)
			ran = l.LimitCancelable(ctx, minOperationTime, func() bool {
				return false // Cancel the operation
			})
			require.False(t, ran)

			// Actually run two operations
			ran = l.Limit(ctx, minOperationTime, func() {})
			require.True(t, ran)
			ran = l.LimitCancelable(ctx, minOperationTime, func() bool {
				return true
			})
			require.True(t, ran)
		})

	})
}

type mockedCancelableRequestLimiter struct {
	cancel               bool
	wasCalled            bool
	onCalled             func()
	onOperationCompleted func(bool)
}

func (m *mockedCancelableRequestLimiter) LimitCancelable(ctx context.Context, minOperationTime time.Duration, operation func() bool) bool {
	m.wasCalled = true

	if m.onCalled != nil {
		m.onCalled()
	}

	if m.cancel {
		return false
	}

	operationStatus := operation()

	if m.onOperationCompleted != nil {
		m.onOperationCompleted(operationStatus)
	}

	return operationStatus
}

func TestComposedRequestLimiter(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	t.Run("init", func(t *testing.T) {
		t.Parallel()
		l1 := ratelimiting.NewWindowLimitRequestLimiter(5, 10*time.Minute, time.Now, time.After)
		l2 := ratelimiting.NewWindowLimitRequestLimiter(5, 10*time.Minute, time.Now, time.After)
		l := ratelimiting.NewComposedRequestLimiter(l1, l2)
		require.NotNil(t, l)
	})

	t.Run("limiters don't share state", func(t *testing.T) {
		t.Parallel()
		l1 := ratelimiting.NewWindowLimitRequestLimiter(1, 1*time.Hour, time.Now, time.After)
		l2 := ratelimiting.NewWindowLimitRequestLimiter(1, 1*time.Hour, time.Now, time.After)
		l3 := ratelimiting.NewWindowLimitRequestLimiter(1, 1*time.Hour, time.Now, time.After)
		l4 := ratelimiting.NewWindowLimitRequestLimiter(1, 1*time.Hour, time.Now, time.After)

		c1 := ratelimiting.NewComposedRequestLimiter(l1, l2)
		c2 := ratelimiting.NewComposedRequestLimiter(l3, l4)
		require.True(t, c1.Limit(ctx, 1*time.Second, func() {}))
		require.True(t, c2.Limit(ctx, 1*time.Second, func() {}))
	})

	t.Run("all composed limiters are called in order", func(t *testing.T) {
		t.Parallel()
		calls := make([]int, 0, 3)
		m1 := &mockedCancelableRequestLimiter{
			onCalled: func() {
				calls = append(calls, 1)
			},
		}
		m2 := &mockedCancelableRequestLimiter{
			onCalled: func() {
				calls = append(calls, 2)
			},
		}
		m3 := &mockedCancelableRequestLimiter{
			onCalled: func() {
				calls = append(calls, 3)
			},
		}

		l := ratelimiting.NewComposedRequestLimiter(m1, m2, m3)
		operationCalled := false
		ran := l.Limit(ctx, 1*time.Second, func() { operationCalled = true })
		require.True(t, ran)

		require.True(t, operationCalled)

		require.True(t, m1.wasCalled)
		require.True(t, m2.wasCalled)
		require.True(t, m3.wasCalled)

		require.Equal(t, []int{1, 2, 3}, calls)
	})

	t.Run("limiters after the canceled one are not called", func(t *testing.T) {
		t.Parallel()
		cases := []struct {
			m1Cancel        bool
			m2Cancel        bool
			m3Cancel        bool
			operationCancel bool

			expectedCalls []int
		}{
			{
				m1Cancel:      false,
				m2Cancel:      false,
				m3Cancel:      false,
				expectedCalls: []int{1, 2, 3, 4},
			},
			{
				m1Cancel:      false,
				m2Cancel:      false,
				m3Cancel:      true,
				expectedCalls: []int{1, 2, 3},
			},
			{
				m1Cancel:      false,
				m2Cancel:      true,
				m3Cancel:      false,
				expectedCalls: []int{1, 2},
			},
			{
				m1Cancel:      false,
				m2Cancel:      true,
				m3Cancel:      true,
				expectedCalls: []int{1, 2},
			},
			{
				m1Cancel:      true,
				m2Cancel:      false,
				m3Cancel:      false,
				expectedCalls: []int{1},
			},
			{
				m1Cancel:      true,
				m2Cancel:      true,
				m3Cancel:      false,
				expectedCalls: []int{1},
			},
			{
				m1Cancel:      true,
				m2Cancel:      false,
				m3Cancel:      true,
				expectedCalls: []int{1},
			},
			{
				m1Cancel:      true,
				m2Cancel:      true,
				m3Cancel:      true,
				expectedCalls: []int{1},
			},
		}

		for _, c := range cases {
			t.Run(
				fmt.Sprintf(
					"m1Cancel=%t,m2Cancel=%t,m3Cancel=%t",
					c.m1Cancel, c.m2Cancel, c.m3Cancel,
				),
				func(t *testing.T) {
					t.Parallel()
					calls := make([]int, 0, 3)

					m1 := &mockedCancelableRequestLimiter{
						cancel: c.m1Cancel,
						onCalled: func() {
							calls = append(calls, 1)
						},
					}
					m2 := &mockedCancelableRequestLimiter{
						cancel: c.m2Cancel,
						onCalled: func() {
							calls = append(calls, 2)
						},
					}
					m3 := &mockedCancelableRequestLimiter{
						cancel: c.m3Cancel,
						onCalled: func() {
							calls = append(calls, 3)
						},
					}
					l := ratelimiting.NewComposedRequestLimiter(m1, m2, m3)

					ran := l.Limit(ctx, 1*time.Second, func() {
						calls = append(calls, 4)
					})
					require.Equal(t, slices.Contains(c.expectedCalls, 4), ran)

					require.Equal(t, c.expectedCalls, calls)
				},
			)
		}
	})

	t.Run("any limiter canceling makes the whole operation cancel", func(t *testing.T) {
		t.Parallel()

		m1 := &mockedCancelableRequestLimiter{
			cancel: false,
			onOperationCompleted: func(ran bool) {
				require.False(t, ran)
			},
		}
		m2 := &mockedCancelableRequestLimiter{
			cancel: true,
			onOperationCompleted: func(ran bool) {
				assert.False(t, true, "operation should not reach this limiter")
			},
		}
		l := ratelimiting.NewComposedRequestLimiter(m1, m2)

		ran := l.Limit(ctx, 1*time.Second, func() {
			assert.False(t, true, "operation should not be called")
		})
		require.False(t, ran)
	})
}
