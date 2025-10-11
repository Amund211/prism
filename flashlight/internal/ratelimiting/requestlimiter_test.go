package ratelimiting_test

import (
	"context"
	"fmt"
	"slices"
	"sync"
	"testing"
	"testing/synctest"
	"time"

	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestWindowLimitRequestLimiter(t *testing.T) {
	t.Parallel()

	t.Run("init", func(t *testing.T) {
		t.Parallel()
		l := ratelimiting.NewWindowLimitRequestLimiter(5, 10*time.Minute, time.Now, time.After)
		require.NotNil(t, l)
	})

	t.Run("limiters don't share state", func(t *testing.T) {
		t.Parallel()
		synctest.Test(t, func(t *testing.T) {
			start := time.Now()
			ctx := t.Context()

			l1 := ratelimiting.NewWindowLimitRequestLimiter(1, 1*time.Hour, time.Now, time.After)
			l2 := ratelimiting.NewWindowLimitRequestLimiter(1, 1*time.Hour, time.Now, time.After)
			l3 := ratelimiting.NewWindowLimitRequestLimiter(1, 1*time.Hour, time.Now, time.After)
			l4 := ratelimiting.NewWindowLimitRequestLimiter(1, 1*time.Hour, time.Now, time.After)

			require.True(t, l1.Limit(ctx, 1*time.Second, func(ctx context.Context) {}))
			require.True(t, l2.Limit(ctx, 1*time.Second, func(ctx context.Context) {}))
			require.True(t, l3.Limit(ctx, 1*time.Second, func(ctx context.Context) {}))
			require.True(t, l4.Limit(ctx, 1*time.Second, func(ctx context.Context) {}))

			// All operations should have run immediately
			require.Equal(t, start, time.Now())
		})
	})

	t.Run("Parallel requests", func(t *testing.T) {
		t.Parallel()

		type request struct {
			startAt       time.Duration
			expectedStart time.Duration
			operationTime time.Duration
		}

		// NOTE: Requests should be issued to make sure there are at most `limit` requests waiting at any time
		//       This makes the tests more predictable, as we can guarantee the order of requests

		cases := []struct {
			name         string
			limit        int
			window       time.Duration
			requests     []request
			totalSeconds int
		}{
			{
				name:     "No requests",
				limit:    2,
				window:   10 * time.Second,
				requests: []request{},
			},
			{
				name:   "All requests fit in the window",
				limit:  10,
				window: 1_000 * time.Second,
				requests: []request{
					{
						startAt:       0 * time.Second,
						expectedStart: 0 * time.Second,
						operationTime: 1 * time.Second,
					},
					{
						startAt:       0 * time.Second,
						expectedStart: 0 * time.Second,
						operationTime: 0 * time.Second,
					},
					{
						startAt:       1 * time.Second,
						expectedStart: 1 * time.Second,
						operationTime: 1 * time.Second,
					},
					{
						startAt:       3 * time.Second,
						expectedStart: 3 * time.Second,
						operationTime: 1 * time.Second,
					},
					{
						startAt:       3 * time.Second,
						expectedStart: 3 * time.Second,
						operationTime: 10 * time.Second,
					},
					{
						startAt:       6 * time.Second,
						expectedStart: 6 * time.Second,
						operationTime: 2 * time.Second,
					},
				},
			},
			{
				name:   "Last request is blocked",
				limit:  3,
				window: 60 * time.Second,
				requests: []request{
					{
						startAt:       0 * time.Second,
						expectedStart: 0 * time.Second,
						operationTime: 1 * time.Second,
					},
					{
						startAt:       1 * time.Second,
						expectedStart: 1 * time.Second,
						operationTime: 1 * time.Second,
					},
					{
						startAt:       2 * time.Second,
						expectedStart: 2 * time.Second,
						operationTime: 1 * time.Second,
					},
					{
						startAt:       3 * time.Second,
						expectedStart: 61 * time.Second,
						operationTime: 1 * time.Second,
					},
				},
			},
			{
				name:   "Multiple concurrent requests",
				limit:  2,
				window: 10 * time.Second,
				requests: []request{
					{
						startAt:       0 * time.Second,
						expectedStart: 0 * time.Second,
						operationTime: 1 * time.Second,
					},
					{
						startAt:       0 * time.Second,
						expectedStart: 0 * time.Second,
						operationTime: 1 * time.Second,
					},
					{
						startAt:       1 * time.Second,
						expectedStart: 11 * time.Second,
						operationTime: 1 * time.Second,
					},
					{
						startAt:       1 * time.Second,
						expectedStart: 11 * time.Second,
						operationTime: 1 * time.Second,
					},
					{
						startAt:       2 * time.Second,
						expectedStart: 22 * time.Second,
						operationTime: 0 * time.Second,
					},
					{
						startAt:       2 * time.Second,
						expectedStart: 22 * time.Second,
						operationTime: 1 * time.Second,
					},
				},
			},
		}

		for _, c := range cases {
			t.Run(c.name, func(t *testing.T) {
				t.Parallel()

				synctest.Test(t, func(t *testing.T) {
					start := time.Now()

					ctx := t.Context()

					l := ratelimiting.NewWindowLimitRequestLimiter(c.limit, c.window, time.Now, time.After)
					minOperationTime := 500 * time.Millisecond // Does not matter since we don't have a deadline

					wg := sync.WaitGroup{}
					for _, req := range c.requests {
						wg.Go(func() {
							t.Helper()

							time.Sleep(req.startAt)

							expectedEnd := start.Add(req.expectedStart + req.operationTime)

							ran := l.Limit(ctx, minOperationTime, func(ctx context.Context) {
								t.Helper()
								require.Equal(t, start.Add(req.expectedStart), time.Now())
								time.Sleep(req.operationTime)
								require.Equal(t, expectedEnd, time.Now())
							})
							require.True(t, ran)

							require.Equal(t, expectedEnd, time.Now())
						})
					}

					wg.Wait() // Ensure all requests have finished
				})
			})
		}
	})

	t.Run("concurrent requests > limit", func(t *testing.T) {
		t.Parallel()
		synctest.Test(t, func(t *testing.T) {
			start := time.Now()
			ctx := t.Context()

			l := ratelimiting.NewWindowLimitRequestLimiter(2, 10*time.Second, time.Now, time.After)
			minOperationTime := 500 * time.Millisecond // Doesn't matter since we don't have a deadline
			operationTime := 1 * time.Second

			requests := 100
			wg := sync.WaitGroup{}
			mutex := sync.Mutex{}
			startedAt := make([]time.Time, 0)

			// These requests should start immediately
			for range requests {
				wg.Go(func() {
					t.Helper()

					ran := l.Limit(ctx, minOperationTime, func(ctx context.Context) {
						t.Helper()

						mutex.Lock()
						startedAt = append(startedAt, time.Now())
						mutex.Unlock()

						time.Sleep(operationTime)
					})
					require.True(t, ran)
				})
			}

			wg.Wait()

			slices.SortFunc(startedAt, func(a, b time.Time) int {
				if a.Before(b) {
					return -1
				} else if a.After(b) {
					return 1
				}
				return 0
			})

			require.Len(t, startedAt, requests)
			for i := range requests {
				batch := i / 2
				waitPerBatch := 10*time.Second + 1*time.Second
				earliestStart := start.Add(time.Duration(batch) * waitPerBatch)
				require.GreaterOrEqual(t, startedAt[i], earliestStart)
			}
		})
	})

	t.Run("request conditionally runs based on context deadline", func(t *testing.T) {
		t.Parallel()
		cases := []struct {
			timeout   time.Duration
			shouldRun bool
		}{
			{1 * time.Second, false},
			{2 * time.Second, false},
			{3 * time.Second, false},
			{4 * time.Second, false},
			{5 * time.Second, false},
			{6 * time.Second, false},
			{7 * time.Second, false},
			{8 * time.Second, false},
			{9 * time.Second, false},
			{10 * time.Second, false},
			{11 * time.Second, false},
			{11*time.Second + 999*time.Millisecond, false},

			{12*time.Second + 1*time.Millisecond, true},
			{15 * time.Second, true},
			{20 * time.Second, true},
			{25 * time.Second, true},
			{30 * time.Second, true},
			{60 * time.Second, true},
		}

		for _, c := range cases {
			t.Run(c.timeout.String(), func(t *testing.T) {
				t.Parallel()
				synctest.Test(t, func(t *testing.T) {
					start := time.Now()
					ctx := t.Context()

					l := ratelimiting.NewWindowLimitRequestLimiter(2, 10*time.Second, time.Now, time.After)
					minOperationTime := 2 * time.Second

					// Exhaust the limiter
					ran := l.Limit(ctx, minOperationTime, func(ctx context.Context) {})
					require.True(t, ran)
					ran = l.Limit(ctx, minOperationTime, func(ctx context.Context) {})
					require.True(t, ran)

					require.Equal(t, start, time.Now())

					ctx, close := context.WithTimeout(t.Context(), c.timeout)
					defer close()
					ran = l.Limit(ctx, minOperationTime, func(ctx context.Context) {
						t.Helper()
						require.True(t, c.shouldRun)
						require.Equal(t, start.Add(10*time.Second), time.Now())
					})

					require.Equal(t, c.shouldRun, ran)
					if c.shouldRun {
						require.Equal(t, start.Add(10*time.Second), time.Now())
					} else {
						require.Equal(t, start, time.Now())
					}
				})
			})
		}
	})

	t.Run("request always runs when there is no wait", func(t *testing.T) {
		// The limiter should not stop any operations from running if there is no wait
		// This applies even if the context deadline is shorter than the max operation time
		t.Parallel()
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
				synctest.Test(t, func(t *testing.T) {
					start := time.Now()
					l := ratelimiting.NewWindowLimitRequestLimiter(2, 10*time.Second, time.Now, time.After)
					minOperationTime := 2 * time.Second

					ctx, close := context.WithTimeout(t.Context(), timeout)
					defer close()
					ran := l.Limit(ctx, minOperationTime, func(ctx context.Context) {})
					require.True(t, ran)

					require.Equal(t, start, time.Now())
				})
			})
		}
	})

	t.Run("cancelling requests works", func(t *testing.T) {
		t.Parallel()

		minOperationTime := 500 * time.Millisecond // Doesn't matter since we don't have a deadline

		t.Run("canceled requests return from waiting for a slot", func(t *testing.T) {
			t.Parallel()
			synctest.Test(t, func(t *testing.T) {
				start := time.Now()
				ctx := t.Context()

				requestsCompletedWg := sync.WaitGroup{}

				requestsWg := sync.WaitGroup{}
				requestsWg.Add(1)

				l := ratelimiting.NewWindowLimitRequestLimiter(2, 10*time.Second, time.Now, time.After)
				// Consume all concurrency from the limiter
				for range 2 {
					requestsCompletedWg.Go(func() {
						ran := l.Limit(ctx, minOperationTime, func(ctx context.Context) {
							requestsWg.Wait()
						})
						require.True(t, ran)
					})
				}

				// Wait for the requests to start and occupy all slots
				synctest.Wait()

				ctx, cancel := context.WithCancel(t.Context())

				requestCanceled := false
				requestsCompletedWg.Go(func() {
					ran := l.Limit(ctx, minOperationTime, func(ctx context.Context) {
						t.Helper()
						assert.False(t, true, "operation should not be called")
					})
					require.False(t, ran)
					requestCanceled = true
				})

				// Wait for the request to start and block on acquiring a slot
				synctest.Wait()

				require.False(t, requestCanceled)

				cancel()

				synctest.Wait()

				require.True(t, requestCanceled)

				// Let the other requests finish
				requestsWg.Done()
				requestsCompletedWg.Wait()

				require.Equal(t, start, time.Now())
			})
		})

		t.Run("canceled requests return from sleep", func(t *testing.T) {
			t.Parallel()

			synctest.Test(t, func(t *testing.T) {
				start := time.Now()
				ctx := t.Context()

				l := ratelimiting.NewWindowLimitRequestLimiter(2, 10*time.Second, time.Now, time.After)
				// Exhaust the limiter
				ran := l.Limit(ctx, minOperationTime, func(ctx context.Context) {})
				require.True(t, ran)
				ran = l.Limit(ctx, minOperationTime, func(ctx context.Context) {})
				require.True(t, ran)

				require.Equal(t, start, time.Now())

				ctx, cancel := context.WithCancel(context.Background())

				limitReturned := false

				go func() {
					ran := l.Limit(ctx, minOperationTime, func(ctx context.Context) {
						t.Helper()
						assert.False(t, true, "operation should not be called")
					})
					require.Equal(t, start.Add(2*time.Second), time.Now())
					limitReturned = true
					require.False(t, ran)
				}()

				// Wait for the request to start and block on After
				synctest.Wait()

				// Pretend like the request has been waiting for 2 seconds before we cancel it
				time.Sleep(2 * time.Second)

				require.False(t, limitReturned)

				cancel()

				synctest.Wait()

				require.True(t, limitReturned)
			})
		})

		t.Run("cancelling requests when acquiring a slot does not affect further requests", func(t *testing.T) {
			t.Parallel()

			synctest.Test(t, func(t *testing.T) {
				start := time.Now()
				ctx := t.Context()

				requestsCompletedWg := sync.WaitGroup{}

				requestsCanRun := make(chan struct{})

				l := ratelimiting.NewWindowLimitRequestLimiter(2, 10*time.Second, time.Now, time.After)

				// Consume all concurrency from the limiter
				for range 2 {
					requestsCompletedWg.Go(func() {
						ran := l.Limit(ctx, minOperationTime, func(ctx context.Context) {
							<-requestsCanRun
						})
						require.True(t, ran)
					})
				}

				// Wait for the requests to start and occupy all slots
				synctest.Wait()

				ctx, cancel := context.WithCancel(context.Background())
				cancel() // Cancel immediately

				canceledRequestsWg := sync.WaitGroup{}
				for range 100 {
					canceledRequestsWg.Go(func() {
						ran := l.Limit(ctx, minOperationTime, func(ctx context.Context) {
							t.Helper()
							assert.False(t, true, "operation should not be called")
						})
						require.False(t, ran)
					})
				}
				canceledRequestsWg.Wait()

				// Let the other requests finish
				close(requestsCanRun)

				requestsCompletedWg.Wait()

				require.Equal(t, start, time.Now())
			})
		})

		t.Run("cancelling requests during sleep does not affect further requests", func(t *testing.T) {
			// A sleeping request has grabbed a slot. Cancelling it should put the slot back
			t.Parallel()

			synctest.Test(t, func(t *testing.T) {
				start := time.Now()
				ctx := t.Context()

				l := ratelimiting.NewWindowLimitRequestLimiter(1, 10*time.Second, time.Now, time.After)

				// Exhaust the limiter
				ran := l.Limit(ctx, minOperationTime, func(ctx context.Context) {})
				require.True(t, ran)
				require.Equal(t, start, time.Now())

				ctxWithCancel, cancel := context.WithCancel(context.Background())
				limitReturned := false
				go func() {
					ran := l.Limit(ctxWithCancel, minOperationTime, func(ctx context.Context) {
						t.Helper()
						assert.False(t, true, "operation should not be called")
					})
					limitReturned = true
					require.False(t, ran)
					require.Equal(t, start.Add(2*time.Second), time.Now())
				}()

				// Wait for the request to start and block on After
				time.Sleep(2 * time.Second)
				require.False(t, limitReturned)

				cancel()
				synctest.Wait()

				require.True(t, limitReturned)

				// Since the request was canceled, we just have to wait for the original request to move outside the window
				ran = l.Limit(ctx, minOperationTime, func(ctx context.Context) {})
				require.True(t, ran)

				require.Equal(t, start.Add(10*time.Second), time.Now())
			})
		})

		t.Run("canceling an operation does not affect further requests", func(t *testing.T) {
			t.Parallel()

			synctest.Test(t, func(t *testing.T) {
				start := time.Now()
				ctx := t.Context()

				l := ratelimiting.NewWindowLimitRequestLimiter(2, 10*time.Second, time.Now, time.After)

				// Exhaust the limiter
				ran := l.Limit(ctx, minOperationTime, func(ctx context.Context) {})
				require.True(t, ran)
				ran = l.Limit(ctx, minOperationTime, func(ctx context.Context) {})
				require.True(t, ran)

				// Move both requests just outside the window
				time.Sleep(10 * time.Second)

				wg := sync.WaitGroup{}
				for range 100 {
					wg.Go(func() {
						ran := l.LimitCancelable(ctx, minOperationTime, func(ctx context.Context) bool {
							return false // Cancel the operation
						})
						require.False(t, ran)
					})
				}
				wg.Wait()

				// Actually run two operations
				ran = l.Limit(ctx, minOperationTime, func(ctx context.Context) {})
				require.True(t, ran)
				ran = l.LimitCancelable(ctx, minOperationTime, func(ctx context.Context) bool {
					return true
				})
				require.True(t, ran)

				require.Equal(t, start.Add(10*time.Second), time.Now())
			})
		})

	})
}

type mockedCancelableRequestLimiter struct {
	cancel               bool
	wasCalled            bool
	onCalled             func()
	onOperationCompleted func(bool)
}

func (m *mockedCancelableRequestLimiter) LimitCancelable(ctx context.Context, minOperationTime time.Duration, operation func(ctx context.Context) bool) bool {
	m.wasCalled = true

	if m.onCalled != nil {
		m.onCalled()
	}

	if m.cancel {
		return false
	}

	operationStatus := operation(ctx)

	if m.onOperationCompleted != nil {
		m.onOperationCompleted(operationStatus)
	}

	return operationStatus
}

func TestComposedRequestLimiter(t *testing.T) {
	t.Parallel()
	ctx := t.Context()

	t.Run("init", func(t *testing.T) {
		t.Parallel()
		l1 := ratelimiting.NewWindowLimitRequestLimiter(5, 10*time.Minute, time.Now, time.After)
		l2 := ratelimiting.NewWindowLimitRequestLimiter(5, 10*time.Minute, time.Now, time.After)
		l := ratelimiting.NewComposedRequestLimiter(l1, l2)
		require.NotNil(t, l)
	})

	t.Run("limiters don't share state", func(t *testing.T) {
		t.Parallel()
		synctest.Test(t, func(t *testing.T) {
			start := time.Now()
			ctx := t.Context()

			l1 := ratelimiting.NewWindowLimitRequestLimiter(1, 1*time.Hour, time.Now, time.After)
			l2 := ratelimiting.NewWindowLimitRequestLimiter(1, 1*time.Hour, time.Now, time.After)
			l3 := ratelimiting.NewWindowLimitRequestLimiter(1, 1*time.Hour, time.Now, time.After)
			l4 := ratelimiting.NewWindowLimitRequestLimiter(1, 1*time.Hour, time.Now, time.After)

			c1 := ratelimiting.NewComposedRequestLimiter(l1, l2)
			c2 := ratelimiting.NewComposedRequestLimiter(l3, l4)
			require.True(t, c1.Limit(ctx, 1*time.Second, func(ctx context.Context) {}))
			require.True(t, c2.Limit(ctx, 1*time.Second, func(ctx context.Context) {}))

			require.Equal(t, start, time.Now())
		})
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
		ran := l.Limit(ctx, 1*time.Second, func(ctx context.Context) { operationCalled = true })
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

					ran := l.Limit(ctx, 1*time.Second, func(ctx context.Context) {
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

		ran := l.Limit(ctx, 1*time.Second, func(ctx context.Context) {
			assert.False(t, true, "operation should not be called")
		})
		require.False(t, ran)
	})
}
