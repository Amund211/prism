package ratelimiting

import (
	"context"
	"runtime"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

type mockedTime struct {
	t           *testing.T
	currentTime time.Time
	timers      []mockedTimer
	lock        sync.Mutex
	afterCalls  atomic.Int32
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
		afterCalls:  atomic.Int32{},
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

	m.afterCalls.Add(1)

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

func TestInsertSortedOrder(t *testing.T) {
	t.Parallel()

	t1 := time.Date(2024, time.January, 1, 0, 0, 0, 0, time.UTC)
	t2 := time.Date(2024, time.January, 2, 0, 0, 0, 0, time.UTC)
	t3 := time.Date(2024, time.January, 3, 0, 0, 0, 0, time.UTC)
	t4 := time.Date(2024, time.January, 4, 0, 0, 0, 0, time.UTC)

	cases := []struct {
		name     string
		arr      []time.Time
		toInsert time.Time
		expected []time.Time
	}{
		{
			name:     "Insert into empty array",
			arr:      []time.Time{},
			toInsert: t1,
			expected: []time.Time{t1},
		},
		{
			name:     "Insert at the beginning",
			arr:      []time.Time{t2, t3, t4},
			toInsert: t1,
			expected: []time.Time{t1, t2, t3, t4},
		},
		{
			name:     "Insert at pos 2",
			arr:      []time.Time{t1, t3, t4},
			toInsert: t2,
			expected: []time.Time{t1, t2, t3, t4},
		},
		{
			name:     "Insert at pos 3",
			arr:      []time.Time{t1, t2, t4},
			toInsert: t3,
			expected: []time.Time{t1, t2, t3, t4},
		},
		{
			name:     "Insert at the end",
			arr:      []time.Time{t1, t2, t3},
			toInsert: t4,
			expected: []time.Time{t1, t2, t3, t4},
		},
		{
			name:     "Insert at the beginning - with duplicates",
			arr:      []time.Time{t1, t2, t3, t4},
			toInsert: t1,
			expected: []time.Time{t1, t1, t2, t3, t4},
		},
		{
			name:     "Insert at pos 2 - with duplicates",
			arr:      []time.Time{t1, t2, t3, t4},
			toInsert: t2,
			expected: []time.Time{t1, t2, t2, t3, t4},
		},
		{
			name:     "Insert at pos 3 - with duplicates",
			arr:      []time.Time{t1, t2, t3, t4},
			toInsert: t3,
			expected: []time.Time{t1, t2, t3, t3, t4},
		},
		{
			name:     "Insert at the end - with duplicates",
			arr:      []time.Time{t1, t2, t3, t4},
			toInsert: t4,
			expected: []time.Time{t1, t2, t3, t4, t4},
		},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			t.Parallel()

			result := insertSortedOrder(c.arr, c.toInsert)
			require.Equal(t, c.expected, result)
		})
	}
}

func TestWindowLimitRequestLimiter(t *testing.T) {
	t.Parallel()

	start := time.Date(2024, time.January, 1, 0, 0, 0, 0, time.UTC)

	type request struct {
		startAt       time.Duration
		waitStarted   time.Time
		expectedStart time.Time
		operationTime time.Duration
	}

	// NOTE: Requests should be issued to make sure there are at most `limit` requests waiting at any time
	//       This makes the tests more predictable, as we can guarantee the order of requests
	runDeadlineFreeTest := func(t *testing.T, limit int, window time.Duration, requests []request, totalSeconds int) {
		t.Helper()

		ctx := context.Background()

		mocked := newMockedTime(t, start)
		l := NewWindowLimitRequestLimiter(limit, window, mocked.Now, mocked.After)
		maxOperationTime := 2 * time.Second // Does not matter since we don't have a deadline

		var testCompleteWg sync.WaitGroup

		issueRequest := func(expectedStart time.Time, operationTime time.Duration) {
			t.Helper()

			expectedEnd := expectedStart.Add(operationTime)

			go func() {
				t.Helper()
				defer testCompleteWg.Done()

				ran := l.Limit(ctx, maxOperationTime, func() {
					t.Helper()
					require.Equal(t, expectedStart, mocked.Now())
					mocked.sleep(operationTime)
					require.Equal(t, expectedEnd, mocked.Now())
				})
				require.True(t, ran)

				require.Equal(t, expectedEnd, mocked.Now())

				// HACK: Add an extra "call" so we can wait for the request to complete
				mocked.afterCalls.Add(1)
			}()
		}

		maxTime := 0
		for _, req := range requests {
			require.GreaterOrEqual(t, int(req.startAt.Seconds()), 0)
			finishedAt := req.expectedStart.Add(req.operationTime)
			maxTime = max(maxTime, int(finishedAt.Sub(start).Seconds()))
		}

		desiredAfterCallsBySecond := make([]int, maxTime+1)
		for _, req := range requests {
			// Calls to Limit fetches slots + waits
			if !req.waitStarted.IsZero() {
				desiredAfterCallsBySecond[int(req.waitStarted.Sub(start).Seconds())]++
			}

			// Sleep in request
			if req.operationTime > 0 {
				desiredAfterCallsBySecond[int(req.expectedStart.Sub(start).Seconds())]++
			}

			// Finishes
			desiredAfterCallsBySecond[int(req.expectedStart.Add(req.operationTime).Sub(start).Seconds())]++
		}

		desiredAfterCalls := func(currentSecond int) int {
			require.GreaterOrEqual(t, currentSecond, 0)
			currentSecond = min(maxTime, currentSecond)

			total := 0
			for i := 0; i <= currentSecond; i++ {
				total += desiredAfterCallsBySecond[i]
			}
			return total
		}

		testCompleteWg.Add(len(requests))

		for second := 0; second < totalSeconds; second++ {
			// Issue requests scheduled for this second
			for _, req := range requests {
				if req.startAt == time.Duration(second)*time.Second {
					issueRequest(req.expectedStart, req.operationTime)
				}
			}

			// Wait for all expected after calls to happen
			secondCompleted := make(chan struct{})
			go func() {
				for int(mocked.afterCalls.Load()) != desiredAfterCalls(second) {
					runtime.Gosched() // Allow other goroutines to run
				}
				close(secondCompleted)
			}()
			select {
			case <-secondCompleted:
				// All good
			case <-time.After(100 * time.Millisecond):
				t.Fatalf("Timeout waiting for after calls at %d seconds: have %d, want %d\n", second, mocked.afterCalls.Load(), desiredAfterCalls(second))
			}

			// Ensure nothing else happens until we advance time
			for i := 0; i < 100; i++ {
				runtime.Gosched() // Allow other goroutines to run
				require.Equal(t, desiredAfterCalls(second), int(mocked.afterCalls.Load()))
			}

			mocked.advance(1 * time.Second)
		}

		testCompleteWg.Wait() // Ensure all requests have finished
	}

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
					expectedStart: start,
					operationTime: 1 * time.Second,
				},
				{
					startAt:       0 * time.Second,
					expectedStart: start,
					operationTime: 0 * time.Second,
				},
				{
					startAt:       1 * time.Second,
					expectedStart: start.Add(1 * time.Second),
					operationTime: 1 * time.Second,
				},
				{
					startAt:       3 * time.Second,
					expectedStart: start.Add(3 * time.Second),
					operationTime: 1 * time.Second,
				},
				{
					startAt:       3 * time.Second,
					expectedStart: start.Add(3 * time.Second),
					operationTime: 10 * time.Second,
				},
				{
					startAt:       6 * time.Second,
					expectedStart: start.Add(6 * time.Second),
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
					expectedStart: start,
					operationTime: 1 * time.Second,
				},
				{
					startAt:       1 * time.Second,
					expectedStart: start.Add(1 * time.Second),
					operationTime: 1 * time.Second,
				},
				{
					startAt:       2 * time.Second,
					expectedStart: start.Add(2 * time.Second),
					operationTime: 1 * time.Second,
				},
				{
					startAt:       3 * time.Second,
					waitStarted:   start.Add(3 * time.Second),
					expectedStart: start.Add(61 * time.Second),
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
					expectedStart: start,
					operationTime: 1 * time.Second,
				},
				{
					startAt:       0 * time.Second,
					expectedStart: start,
					operationTime: 1 * time.Second,
				},
				{
					startAt:       1 * time.Second,
					waitStarted:   start.Add(1 * time.Second),
					expectedStart: start.Add(11 * time.Second),
					operationTime: 1 * time.Second,
				},
				{
					startAt:       1 * time.Second,
					waitStarted:   start.Add(1 * time.Second),
					expectedStart: start.Add(11 * time.Second),
					operationTime: 1 * time.Second,
				},
				{
					startAt:       2 * time.Second,
					waitStarted:   start.Add(12 * time.Second),
					expectedStart: start.Add(22 * time.Second),
					operationTime: 0 * time.Second,
				},
				{
					startAt:       2 * time.Second,
					waitStarted:   start.Add(12 * time.Second),
					expectedStart: start.Add(22 * time.Second),
					operationTime: 1 * time.Second,
				},
			},
		},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			t.Parallel()
			totalSeconds := 100
			if c.totalSeconds != 0 {
				totalSeconds = c.totalSeconds
			}

			runDeadlineFreeTest(t, c.limit, c.window, c.requests, totalSeconds)
		})
	}
}
