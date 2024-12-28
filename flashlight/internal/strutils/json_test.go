package strutils_test

import (
	"testing"

	"github.com/Amund211/flashlight/internal/strutils"
	"github.com/stretchr/testify/require"
)

func TestJSONStringsEqual(t *testing.T) {
	tests := []struct {
		name    string
		a       []byte
		b       []byte
		want    bool
		wantErr bool
	}{
		{
			name:    "identical strings",
			a:       []byte(`{"a": 1, "b": 2}`),
			b:       []byte(`{"a": 1, "b": 2}`),
			want:    true,
			wantErr: false,
		},
		{
			name: "different whitespace",
			a:    []byte(`{"a": 1, "b":         2}`),
			b: []byte(`{"a": 	 1, "b": 2
			}`),
			want:    true,
			wantErr: false,
		},
		{
			name:    "different order",
			a:       []byte(`{"a": 1, "b": 2}`),
			b:       []byte(`{"b": 2, "a": 1}`),
			want:    true,
			wantErr: false,
		},
		{
			name:    "complex object",
			a:       []byte(`{"a":1,"b":"str","1":[1,2,3],"2":{"a":1,"b":2}}`),
			b:       []byte(`{"a":	1, "1": [1, 2, 3], "2": {"a": 1, "b": 2}, "b": "str"}`),
			want:    true,
			wantErr: false,
		},
		{
			name:    "missing key",
			a:       []byte(`{"a": 1, "b": 2}`),
			b:       []byte(`{"a": 1}`),
			want:    false,
			wantErr: false,
		},
		{
			name:    "nested different value",
			a:       []byte(`{"a": 1, "b": [{"a": 1, "b": 2}]}`),
			b:       []byte(`{"a": 1, "b": [{"a": 1, "b": 3}]}`),
			want:    false,
			wantErr: false,
		},
		{
			name:    "equal numbers",
			a:       []byte(`1`),
			b:       []byte(`1`),
			want:    true,
			wantErr: false,
		},
		{
			name:    "different numbers",
			a:       []byte(`1`),
			b:       []byte(`2`),
			want:    false,
			wantErr: false,
		},
		{
			name:    "equal strings",
			a:       []byte(`"mystring"`),
			b:       []byte(`"mystring"`),
			want:    true,
			wantErr: false,
		},
		{
			name:    "different strings",
			a:       []byte(`"mystring"`),
			b:       []byte(`"myotherstring"`),
			want:    false,
			wantErr: false,
		},
		{
			name:    "equal lists",
			a:       []byte(`["mystring", 1, 2, [1]]`),
			b:       []byte(`["mystring", 1, 2, [1]]`),
			want:    true,
			wantErr: false,
		},
		{
			name:    "different lists",
			a:       []byte(`["mystring", 1, 2, [1]]`),
			b:       []byte(`["mystring", 1, 2, [2]]`),
			want:    false,
			wantErr: false,
		},
		{
			name:    "invalid json",
			a:       []byte(`rawstring`),
			b:       []byte(`[]`),
			want:    false,
			wantErr: true,
		},
		{
			name:    "invalid object",
			a:       []byte(`{"a": 1,}`),
			b:       []byte(`[]`),
			want:    false,
			wantErr: true,
		},
	}

	runTest := func(t *testing.T, a, b []byte, want bool, wantErr bool) {
		t.Helper()
		got, err := strutils.JSONStringsEqual(a, b)
		require.Equal(t, want, got)
		require.Equal(t, wantErr, err != nil)
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			runTest(t, tc.a, tc.b, tc.want, tc.wantErr)
		})
		t.Run(tc.name+" (reversed)", func(t *testing.T) {
			runTest(t, tc.b, tc.a, tc.want, tc.wantErr)
		})
	}
}
