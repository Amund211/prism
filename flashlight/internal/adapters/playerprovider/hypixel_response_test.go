package playerprovider

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path"
	"testing"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/strutils"

	"github.com/stretchr/testify/require"
)

type hypixelAPIResponseToPlayerTest struct {
	name               string
	uuid               string
	queriedAt          time.Time
	hypixelAPIResponse []byte
	hypixelStatusCode  int
	result             *domain.PlayerPIT
	error              error
}

const hypixelAPIResponsesDir = "../../../fixtures/hypixel_api_responses/"
const expectedPlayersDir = "testdata/expected_players/"

var errAnyError = fmt.Errorf("any error")

func runHypixelAPIResponseToPlayerTest(t *testing.T, test hypixelAPIResponseToPlayerTest) {
	t.Helper()

	player, err := HypixelAPIResponseToPlayerPIT(context.Background(), test.uuid, test.queriedAt, test.hypixelAPIResponse, test.hypixelStatusCode)
	if test.error != nil {
		if errors.Is(test.error, errAnyError) {
			// The test just expects there to be any error
			require.Error(t, err)
			return
		}

		require.ErrorIs(t, err, test.error)
		return
	}
	require.NoError(t, err)

	if test.result == nil {
		require.Nil(t, player)
		return
	}
	require.NotNil(t, player)

	// Check that times are equal while ignoring irrelevant differences in the time.Time struct
	require.WithinDuration(t, test.result.QueriedAt, player.QueriedAt, 0)
	player.QueriedAt = test.result.QueriedAt

	if test.result.LastLogin != nil {
		require.NotNil(t, player.LastLogin)
		require.WithinDuration(t, *test.result.LastLogin, *player.LastLogin, 0)
		player.LastLogin = test.result.LastLogin
	}
	if test.result.LastLogout != nil {
		require.NotNil(t, player.LastLogout)
		require.WithinDuration(t, *test.result.LastLogout, *player.LastLogout, 0)
		player.LastLogout = test.result.LastLogout
	}

	require.Equal(t, *test.result, *player)
}

func TestHypixelAPIResponseToPlayerPIT(t *testing.T) {
	t.Parallel()
	t.Run("literals", func(t *testing.T) {
		t.Parallel()

		now := time.Now()
		later := now.Add(1 * time.Hour)

		literalTests := []hypixelAPIResponseToPlayerTest{
			{name: "empty object", hypixelAPIResponse: []byte(`{}`), error: errAnyError},
			{name: "empty list", hypixelAPIResponse: []byte(`[]`), error: errAnyError},
			{name: "empty string", hypixelAPIResponse: []byte(``), error: errAnyError},
			{
				name:      "float experience",
				uuid:      "12345678-90ab-cdef-1234-567890abcdef",
				queriedAt: now,
				hypixelAPIResponse: []byte(`{
					"success": true,
					"player": {
						"uuid":"1234567890abcdef1234567890abcdef",
						"stats": {
							"Bedwars": {
								"Experience": 1087.0
							}
						}
					}
				}`),
				hypixelStatusCode: 200,
				result: &domain.PlayerPIT{
					QueriedAt:  now,
					UUID:       "12345678-90ab-cdef-1234-567890abcdef",
					Experience: 1087,
				},
			},
			{
				name:      "float experience - scientific notation",
				uuid:      "12345678-90ab-cdef-1234-567890abcdef",
				queriedAt: later,
				hypixelAPIResponse: []byte(`{
					"success": true,
					"player": {
						"uuid":"1234567890abcdef1234567890abcdef",
						"stats": {
							"Bedwars": {
								"Experience": 1.2227806E7
							}
						}
					}
				}`),
				hypixelStatusCode: 200,
				result: &domain.PlayerPIT{
					QueriedAt:  later,
					UUID:       "12345678-90ab-cdef-1234-567890abcdef",
					Experience: 12227806,
				},
			},
			{
				name:               "not found",
				uuid:               "12345678-90ab-cdef-1234-567890abcdef",
				queriedAt:          now,
				hypixelAPIResponse: []byte(`{"success": true, "player": null}`),
				hypixelStatusCode:  200,
				error:              domain.ErrPlayerNotFound,
			},
			{
				name:               "hypixel 500",
				uuid:               "12345678-90ab-cdef-1234-567890abcdef",
				queriedAt:          now,
				hypixelAPIResponse: []byte(`{"success":false,"cause":"Internal error"}`),
				hypixelStatusCode:  500,
				error:              domain.ErrTemporarilyUnavailable,
			},
			// The "hypixel weird" cases are just made up to test status code handling
			{
				name:               "hypixel weird 100",
				uuid:               "12345678-90ab-cdef-1234-567890abcdef",
				queriedAt:          now,
				hypixelAPIResponse: []byte(`{"success": true, "player": null}`),
				hypixelStatusCode:  100,
				error:              errAnyError,
			},
			{
				name:               "hypixel weird 204",
				uuid:               "12345678-90ab-cdef-1234-567890abcdef",
				queriedAt:          now,
				hypixelAPIResponse: []byte(`{"success": true, "player": null}`),
				hypixelStatusCode:  204,
				error:              errAnyError,
			},
			{
				name:               "hypixel weird 301",
				uuid:               "12345678-90ab-cdef-1234-567890abcdef",
				queriedAt:          now,
				hypixelAPIResponse: []byte(`{"success": true, "player": null}`),
				hypixelStatusCode:  301,
				error:              errAnyError,
			},
			{
				name:               "hypixel weird 418",
				uuid:               "12345678-90ab-cdef-1234-567890abcdef",
				queriedAt:          now,
				hypixelAPIResponse: []byte(`{"success": true, "player": null}`),
				hypixelStatusCode:  418,
				error:              errAnyError,
			},
			{
				name:               "hypixel weird 508",
				uuid:               "12345678-90ab-cdef-1234-567890abcdef",
				queriedAt:          now,
				hypixelAPIResponse: []byte(`{"success": true, "player": null}`),
				hypixelStatusCode:  508,
				error:              errAnyError,
			},
		}

		cloudflareTests := []hypixelAPIResponseToPlayerTest{}
		for _, statusCode := range []int{502, 503, 504, 520, 521, 522, 523, 524, 525, 526, 527, 530} {
			cloudflareTests = append(cloudflareTests, hypixelAPIResponseToPlayerTest{
				name:               fmt.Sprintf("cloudflare %d", statusCode),
				uuid:               "12345678-90ab-cdef-1234-567890abcdef",
				queriedAt:          now,
				hypixelAPIResponse: []byte(fmt.Sprintf("error code: %d", statusCode)),
				hypixelStatusCode:  statusCode,
				error:              domain.ErrTemporarilyUnavailable,
			})
		}

		for _, test := range append(literalTests, cloudflareTests...) {
			test := test
			t.Run(test.name, func(t *testing.T) {
				runHypixelAPIResponseToPlayerTest(t, test)
			})
		}
	})

	t.Run("fixtures", func(t *testing.T) {
		t.Parallel()

		queriedAt, err := time.Parse(time.RFC3339, "2021-11-25T23:33:47+01:00")
		require.NoError(t, err)

		hypixelAPIResponseFiles, err := os.ReadDir(hypixelAPIResponsesDir)
		require.NoError(t, err)
		hypixelResponseFileNames := make([]string, 0, len(hypixelAPIResponseFiles))
		for _, file := range hypixelAPIResponseFiles {
			if file.IsDir() {
				continue
			}
			hypixelResponseFileNames = append(hypixelResponseFileNames, file.Name())
		}

		expectedPlayerFiles, err := os.ReadDir(expectedPlayersDir)
		require.NoError(t, err)
		expectedPlayerFileNames := make([]string, 0, len(expectedPlayerFiles))
		for _, file := range expectedPlayerFiles {
			if file.IsDir() {
				continue
			}
			expectedPlayerFileNames = append(expectedPlayerFileNames, file.Name())
		}

		require.ElementsMatch(
			t,
			hypixelResponseFileNames,
			expectedPlayerFileNames,
			"All hypixel api response files must have a corresponding expected player file",
		)

		for _, name := range hypixelResponseFileNames {
			t.Run(name, func(t *testing.T) {
				t.Parallel()
				hypixelAPIResponse, err := os.ReadFile(path.Join(hypixelAPIResponsesDir, name))
				require.NoError(t, err)
				expectedPlayerJSON, err := os.ReadFile(path.Join(expectedPlayersDir, name))
				require.NoError(t, err)

				// Parse expected players from go default JSON serialization of the struct
				expectedPlayer := &domain.PlayerPIT{}
				err = json.Unmarshal(expectedPlayerJSON, expectedPlayer)
				require.NoError(t, err)

				// Read UUID
				parsedAPIResponse, err := ParseHypixelAPIResponse(context.Background(), hypixelAPIResponse)
				require.NoError(t, err)
				uuid := "12345678-1234-1234-1234-12345678abcd"
				if parsedAPIResponse.Player != nil && parsedAPIResponse.Player.UUID != nil {
					normalizedUUID, err := strutils.NormalizeUUID(*parsedAPIResponse.Player.UUID)
					require.NoError(t, err)
					uuid = normalizedUUID
				}

				runHypixelAPIResponseToPlayerTest(t,
					hypixelAPIResponseToPlayerTest{
						name:               name,
						uuid:               uuid,
						queriedAt:          queriedAt,
						hypixelAPIResponse: hypixelAPIResponse,
						hypixelStatusCode:  200,
						result:             expectedPlayer,
					},
				)
			})
		}
	})
}
