package ratelimiting

import (
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

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
