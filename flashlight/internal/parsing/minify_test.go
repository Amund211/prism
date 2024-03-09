package parsing

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path"
	"sync"
	"testing"

	"github.com/stretchr/testify/assert"
)

type minifyPlayerDataTest struct {
	name   string
	before []byte
	after  []byte
	error  bool
}

const minifyFixtureDir = "fixtures/"

// NOTE: for readability, after is compacted before being compared
var literalTests = []minifyPlayerDataTest{
	{name: "empty object", before: []byte(`{}`), after: []byte(`{"success":false,"player":null}`)},
	{name: "empty list", before: []byte(`[]`), after: []byte{}, error: true},
	{name: "empty string", before: []byte(``), after: []byte{}, error: true},
	{
		name: "float experience",
		before: []byte(`{
			"success": true,
			"player": {
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
				"stats": {
					"Bedwars": {
						"Experience": 12227806
					}
				}
			}
		}`),
	},
}

func parsePlayerDataFile(filePath string) (minifyPlayerDataTest, error) {
	data, err := os.ReadFile(filePath)
	if err != nil {
		return minifyPlayerDataTest{}, err
	}
	lines := bytes.Split(data, []byte("\n"))
	if len(lines) != 2 {
		return minifyPlayerDataTest{}, fmt.Errorf("File %s does not contain 2 lines", filePath)
	}
	return minifyPlayerDataTest{name: fmt.Sprintf("<%s>", filePath), before: lines[0], after: lines[1]}, nil
}

func runMinifyPlayerDataTest(t *testing.T, test minifyPlayerDataTest) {
	minified, err := MinifyPlayerData(test.before)

	if test.error {
		assert.NotNil(t, err, "minifyPlayerData(%s) - expected error", test.name)
		return
	}

	assert.Nil(t, err, "minifyPlayerData(%s) - unexpected error: %v", test.name, err)
	assert.Equal(t, string(test.after), string(minified), "minifyPlayerData(%s) - expected '%s', got '%s'", test.name, test.after, minified)
}

func TestMinifyPlayerDataLiterals(t *testing.T) {
	for _, test := range literalTests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			if !test.error {
				var compacted bytes.Buffer
				err := json.Compact(&compacted, test.after)
				assert.Nil(t, err, "minifyPlayerData(%s): Error compacting JSON: %v", test.name, err)
				test.after = compacted.Bytes()
			}

			// Real test
			runMinifyPlayerDataTest(t, test)

			if !test.error {
				// Test that minification is idempotent
				test.before = test.after
				test.name = test.name + " (minified)"
				runMinifyPlayerDataTest(t, test)
			}
		})
	}
}

func TestMinifyPlayerDataFiles(t *testing.T) {
	files, err := os.ReadDir(minifyFixtureDir)

	assert.Nil(t, err, "Error reading fixtures directory: %v", err)

	wg := sync.WaitGroup{}
	wg.Add(len(files))

	for _, file := range files {
		file := file
		if file.IsDir() {
			continue
		}
		go func() {
			filePath := path.Join(minifyFixtureDir, file.Name())
			test, err := parsePlayerDataFile(filePath)
			assert.Nil(t, err, "Error parsing file %s: %v", filePath, err)
			// Real test
			runMinifyPlayerDataTest(t, test)

			// Test that minification is idempotent
			test.before = test.after
			test.name = test.name + " (minified)"
			runMinifyPlayerDataTest(t, test)
			wg.Done()
		}()
	}

	wg.Wait()
}
