package accountprovider

import (
	"bytes"
	"errors"
	"io"
	"net/http"
	"testing"
	"time"

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
		queriedAt  time.Time
		expected   domain.Account
		err        error
	}{
		{
			name: "Real valid response",
			response: []byte(`{
  "id" : "a937646bf11544c38dbf9ae4a65669a0",
  "name" : "Skydeath"
}`),
			statusCode: 200,
			queriedAt:  time.Date(2023, 10, 1, 12, 0, 0, 0, time.UTC),
			expected: domain.Account{
				UUID:      "a937646b-f115-44c3-8dbf-9ae4a65669a0",
				Username:  "Skydeath",
				QueriedAt: time.Date(2023, 10, 1, 12, 0, 0, 0, time.UTC),
			},
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
			t.Parallel()

			account, err := accountFromMojangResponse(tc.statusCode, tc.response, tc.queriedAt)
			if tc.err != nil {
				if errors.Is(tc.err, assert.AnError) {
					require.Error(t, err)
				} else {
					require.ErrorIs(t, err, tc.err)
				}
				return
			}
			require.NoError(t, err)

			require.Equal(t, tc.expected, account)
			require.True(t, strutils.UUIDIsNormalized(account.UUID))
		})
	}
}

type mockedClient struct {
	responseData []byte
	statusCode   int
	err          error
}

func (m *mockedClient) Do(req *http.Request) (*http.Response, error) {
	if m.err != nil {
		return nil, m.err
	}

	return &http.Response{
		StatusCode: m.statusCode,
		Body:       io.NopCloser(bytes.NewReader(m.responseData)),
		Header:     make(http.Header),
	}, nil
}

func TestMojang(t *testing.T) {
	ctx := t.Context()

	now := time.Date(2023, 10, 1, 12, 0, 0, 0, time.UTC)
	mockedNow := func() time.Time {
		return now
	}

	client := &mockedClient{
		responseData: []byte(`{
  "id" : "a937646bf11544c38dbf9ae4a65669a0",
  "name" : "Skydeath"
}`),
		statusCode: 200,
	}
	provider := NewMojang(client, mockedNow, time.After)

	account, err := provider.GetAccountByUUID(ctx, "a937646b-f115-44c3-8dbf-9ae4a65669a0")
	require.NoError(t, err)
	require.Equal(t, domain.Account{
		UUID:      "a937646b-f115-44c3-8dbf-9ae4a65669a0",
		Username:  "Skydeath",
		QueriedAt: now,
	}, account)

	account, err = provider.GetAccountByUsername(ctx, "skydeath")
	require.NoError(t, err)
	require.Equal(t, domain.Account{
		UUID:      "a937646b-f115-44c3-8dbf-9ae4a65669a0",
		Username:  "Skydeath",
		QueriedAt: now,
	}, account)

	client.err = assert.AnError

	_, err = provider.GetAccountByUUID(ctx, "a937646b-f115-44c3-8dbf-9ae4a65669a0")
	require.ErrorIs(t, err, assert.AnError)

	_, err = provider.GetAccountByUsername(ctx, "skydeath")
	require.ErrorIs(t, err, assert.AnError)
}
