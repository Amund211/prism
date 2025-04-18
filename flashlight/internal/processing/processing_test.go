package processing

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path"
	"testing"
	"time"

	e "github.com/Amund211/flashlight/internal/errors"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type processPlayerDataTest struct {
	name               string
	before             []byte
	hypixelStatusCode  int
	after              []byte
	expectedStatusCode int
	error              error
	toDomainError      error
}

const hypixelAPIResponsesDir = "../../fixtures/hypixel_api_responses/"
const expectedMinifiedDataDir = "testdata/expected_minified_data/"

// NOTE: for readability, after is compacted before being compared
var literalTests = []processPlayerDataTest{
	{name: "empty object", before: []byte(`{}`), toDomainError: e.APIServerError},
	{name: "empty list", before: []byte(`[]`), after: []byte{}, error: e.APIServerError},
	{name: "empty string", before: []byte(``), after: []byte{}, error: e.APIServerError},
	{
		name: "float experience",
		before: []byte(`{
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
		after: []byte(`{
			"success": true,
			"player": {
				"uuid":"1234567890abcdef1234567890abcdef",
				"stats": {
					"Bedwars": {
						"Experience": 1087
					}
				}
			}
		}`),
	},
	{
		name: "float experience - scientific notation",
		before: []byte(`{
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
		after: []byte(`{
			"success": true,
			"player": {
				"uuid":"1234567890abcdef1234567890abcdef",
				"stats": {
					"Bedwars": {
						"Experience": 12227806
					}
				}
			}
		}`),
	},
	{
		name:               "not found",
		before:             []byte(`{"success": true, "player": null}`),
		after:              []byte(`{"success": true, "player": null}`),
		expectedStatusCode: 404,
	},
	{
		name:              "hypixel 500",
		before:            []byte(`{"success":false,"cause":"Internal error"}`),
		hypixelStatusCode: 500,
		error:             e.RetriableError,
	},
	// The "hypixel weird" cases are just made up to test status code handling
	{
		name:              "hypixel weird 100",
		before:            []byte(`{"success": true, "player": null}`),
		hypixelStatusCode: 100,
		error:             e.APIServerError,
	},
	{
		name:              "hypixel weird 204",
		before:            []byte(`{"success": true, "player": null}`),
		hypixelStatusCode: 204,
		error:             e.APIServerError,
	},
	{
		name:              "hypixel weird 301",
		before:            []byte(`{"success": true, "player": null}`),
		hypixelStatusCode: 301,
		error:             e.APIServerError,
	},
	{
		name:              "hypixel weird 418",
		before:            []byte(`{"success": true, "player": null}`),
		hypixelStatusCode: 418,
		error:             e.APIServerError,
	},
	{
		name:              "hypixel weird 508",
		before:            []byte(`{"success": true, "player": null}`),
		hypixelStatusCode: 508,
		error:             e.APIServerError,
	},
}

func runProcessPlayerDataTest(t *testing.T, test processPlayerDataTest) {
	t.Helper()

	hypixelStatusCode := 200
	if test.hypixelStatusCode != 0 {
		hypixelStatusCode = test.hypixelStatusCode
	}
	expectedStatusCode := 200
	if test.expectedStatusCode != 0 {
		expectedStatusCode = test.expectedStatusCode
	}

	parsedResponse, statusCode, err := ParseHypixelAPIResponse(context.Background(), test.before, hypixelStatusCode)
	if test.error != nil {
		assert.Equal(t, 0, test.expectedStatusCode, "status code not returned on error")
		assert.ErrorIs(t, err, test.error, "processPlayerData(%s) - expected error", test.name)
		return
	}
	require.NoError(t, err)

	domainPlayer, err := HypixelAPIResponseToDomainPlayer(parsedResponse, time.Now(), nil)
	if test.toDomainError != nil {
		require.ErrorIs(t, err, test.toDomainError)
		return
	}
	require.NoError(t, err)
	responseFromDomain := DomainPlayerToHypixelAPIResponse(domainPlayer)

	minified, err := MarshalPlayerData(context.Background(), responseFromDomain)

	assert.Nil(t, err, "processPlayerData(%s) - unexpected marshall error: %v", test.name, err)
	assert.Equal(t, expectedStatusCode, statusCode, test.name)
	assert.Equal(t, string(test.after), string(minified), "processPlayerData(%s) - expected '%s', got '%s'", test.name, test.after, minified)
}

func TestProcessPlayerDataLiterals(t *testing.T) {
	t.Parallel()

	cloudfareTests := []processPlayerDataTest{}
	for _, statusCode := range []int{502, 503, 504, 520, 521, 522, 523, 524, 525, 526, 527, 530} {
		cloudfareTests = append(cloudfareTests, processPlayerDataTest{
			name:              fmt.Sprintf("cloudflare %d", statusCode),
			before:            []byte(fmt.Sprintf("error code: %d", statusCode)),
			hypixelStatusCode: statusCode,
			error:             e.RetriableError,
		})
	}

	for _, test := range append(literalTests, cloudfareTests...) {
		test := test
		t.Run(test.name, func(t *testing.T) {
			if test.error == nil && test.toDomainError == nil {
				var compacted bytes.Buffer
				err := json.Compact(&compacted, test.after)
				assert.Nil(t, err, "processPlayerData(%s): Error compacting JSON: %v", test.name, err)
				test.after = compacted.Bytes()
			}

			// Real test
			runProcessPlayerDataTest(t, test)

			if test.error == nil && test.toDomainError == nil {
				// Test that minification is idempotent
				test.before = test.after
				test.name = test.name + " (minified)"
				runProcessPlayerDataTest(t, test)
			}
		})
	}
}

func TestProcessPlayerDataFiles(t *testing.T) {
	t.Parallel()

	hypixelAPIResponseFiles, err := os.ReadDir(hypixelAPIResponsesDir)
	require.NoError(t, err)
	hypixelResponseFileNames := make([]string, 0, len(hypixelAPIResponseFiles))
	for _, file := range hypixelAPIResponseFiles {
		if file.IsDir() {
			continue
		}
		hypixelResponseFileNames = append(hypixelResponseFileNames, file.Name())
	}

	expectedMinifiedDataFiles, err := os.ReadDir(expectedMinifiedDataDir)
	require.NoError(t, err)
	expectedMinifiedDataFileNames := make([]string, 0, len(expectedMinifiedDataFiles))
	for _, file := range expectedMinifiedDataFiles {
		if file.IsDir() {
			continue
		}
		expectedMinifiedDataFileNames = append(expectedMinifiedDataFileNames, file.Name())
	}

	require.ElementsMatch(
		t,
		hypixelResponseFileNames,
		expectedMinifiedDataFileNames,
		"All hypixel api response files must have a corresponding minified data file",
	)

	for _, name := range hypixelResponseFileNames {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			hypixelAPIResponse, err := os.ReadFile(path.Join(hypixelAPIResponsesDir, name))
			require.NoError(t, err)
			expectedMinifiedData, err := os.ReadFile(path.Join(expectedMinifiedDataDir, name))
			require.NoError(t, err)

			// Real test
			t.Run("real->minified", func(t *testing.T) {
				t.Parallel()
				runProcessPlayerDataTest(t,
					processPlayerDataTest{
						name:   name,
						before: hypixelAPIResponse,
						after:  expectedMinifiedData,
					},
				)
			})

			// Test that minification is idempotent
			t.Run("minified->minified", func(t *testing.T) {
				t.Parallel()
				runProcessPlayerDataTest(t,
					processPlayerDataTest{
						name:   fmt.Sprintf("%s (minified)", name),
						before: expectedMinifiedData,
						after:  expectedMinifiedData,
					},
				)
			})
		})
	}
}
