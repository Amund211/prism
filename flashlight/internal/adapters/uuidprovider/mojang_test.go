package uuidprovider

import (
	"errors"
	"testing"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/strutils"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestUUIDFromMojangResponse(t *testing.T) {
	tests := []struct {
		name       string
		response   []byte
		statusCode int
		expected   string
		err        error
	}{
		{
			name: "Real valid response",
			response: []byte(`{
  "id" : "a937646bf11544c38dbf9ae4a65669a0",
  "name" : "Skydeath"
}`),
			statusCode: 200,
			expected:   "a937646b-f115-44c3-8dbf-9ae4a65669a0",
		},
		{
			name: "Real not found response",
			response: []byte(`{
  "path" : "/users/profiles/minecraft/somenickeduser",
  "errorMessage" : "Couldn't find any profile with name somenickeduser"
}`),
			statusCode: 404,
			err:        domain.ErrUsernameNotFound,
		},
		{
			name: "Real not too many requests response",
			response: []byte(`{
  "path" : "/users/profiles/minecraft/Dinnerbone"
}`),
			statusCode: 429,
			err:        domain.ErrTemporarilyUnavailable,
		},
		// Made up responses
		{
			name:       "204 no body",
			response:   []byte(``),
			statusCode: 204,
			err:        domain.ErrUsernameNotFound,
		},
		{
			name:       "404 no body",
			response:   []byte(``),
			statusCode: 404,
			err:        domain.ErrUsernameNotFound,
		},
		{
			name:       "429 no body",
			response:   []byte(``),
			statusCode: 429,
			err:        domain.ErrTemporarilyUnavailable,
		},
		{
			name:       "503 no body",
			response:   []byte(``),
			statusCode: 503,
			err:        domain.ErrTemporarilyUnavailable,
		},
		{
			name:       "504 no body",
			response:   []byte(``),
			statusCode: 504,
			err:        domain.ErrTemporarilyUnavailable,
		},
		{
			name:       "Invalid JSON",
			response:   []byte(`{"id":"invalid-json"`),
			statusCode: 200,
			err:        assert.AnError,
		},
		{
			name:       "Empty Response",
			response:   []byte(``),
			statusCode: 200,
			err:        assert.AnError,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			uuid, err := uuidFromMojangResponse(tc.statusCode, tc.response)
			if tc.err != nil {
				if errors.Is(tc.err, assert.AnError) {
					require.Error(t, err)
				} else {
					require.ErrorIs(t, err, tc.err)
				}
				return
			}
			require.NoError(t, err)

			require.Equal(t, tc.expected, uuid)
			require.True(t, strutils.UUIDIsNormalized(uuid))
		})
	}
}
