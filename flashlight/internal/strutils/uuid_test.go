package strutils_test

import (
	"testing"

	"github.com/Amund211/flashlight/internal/strutils"
	"github.com/stretchr/testify/require"
)

const INVALID_CHARACTER = "invalid character in UUID"
const BAD_LENGTH = "normalized UUID has incorrect length"

func TestNormalizeUUID(t *testing.T) {
	t.Parallel()

	cases := []struct {
		input          string
		expected       string
		errorSubstring string
	}{
		{
			// Regular dashed UUID
			input:    "01234567-89ab-cdef-0123-456789abcdef",
			expected: "01234567-89ab-cdef-0123-456789abcdef",
		},
		{
			// All caps dashed UUID
			input:    "01234567-89AB-CDEF-0123-456789ABCDEF",
			expected: "01234567-89ab-cdef-0123-456789abcdef",
		},
		{
			// Mixed case dashed UUID
			input:    "01234567-89ab-cdef-0123-456789ABCDEF",
			expected: "01234567-89ab-cdef-0123-456789abcdef",
		},
		{
			// Regular stripped UUID
			input:    "0123456789abcdef0123456789abcdef",
			expected: "01234567-89ab-cdef-0123-456789abcdef",
		},
		{
			// All caps stripped UUID
			input:    "0123456789ABCDEF0123456789ABCDEF",
			expected: "01234567-89ab-cdef-0123-456789abcdef",
		},
		{
			// Mixed case stripped UUID
			input:    "0123456789ABCDEF0123456789abcdef",
			expected: "01234567-89ab-cdef-0123-456789abcdef",
		},
		{
			// Partially stripped UUID
			input:    "01234567-89abcdef-0123456789abcdef",
			expected: "01234567-89ab-cdef-0123-456789abcdef",
		},
		{
			// Weird dashes
			input:    "---------0123---------4567-89------------------abcdef-012345---------6789abcdef---------",
			expected: "01234567-89ab-cdef-0123-456789abcdef",
		},
		{
			input:          "0123456789ABCDEF0123456789abcdex",
			errorSubstring: INVALID_CHARACTER,
		},
		{
			input:          "0123456789xBCDEF0123456789abcdef",
			errorSubstring: INVALID_CHARACTER,
		},
		{
			// Too long
			input:          "01234567-89ab-cdef-0123-456789abcdef-0",
			errorSubstring: BAD_LENGTH,
		},
		{
			// Too short
			input:          "01234567-89ab-cdef-0123-456789abcde",
			errorSubstring: BAD_LENGTH,
		},
	}

	for _, input := range `—ghijklmnopqrstuvwxyzGHIJKLMNOPQRSTUVWXYZ!@#$%^&*()_+[]{}|;':",.<>?/` {
		cases = append(cases, struct {
			input          string
			expected       string
			errorSubstring string
		}{
			input:          string(input),
			errorSubstring: INVALID_CHARACTER,
		})
	}

	for _, tc := range cases {
		require.True(t, tc.expected != "" || tc.errorSubstring != "", "test case must expect a value or an error")
		t.Run(tc.input, func(t *testing.T) {
			t.Parallel()

			actual, err := strutils.NormalizeUUID(tc.input)

			if tc.errorSubstring != "" {
				require.Contains(t, err.Error(), tc.errorSubstring)
				return
			}

			require.NoError(t, err)
			require.Equal(t, tc.expected, actual)
		})
	}
}
