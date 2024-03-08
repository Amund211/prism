package parsing

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path"
	"testing"
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
		if err == nil {
			t.Errorf("minifyPlayerData(%s) - expected error", test.name)
		}
		return
	}

	if err != nil {
		t.Errorf("minifyPlayerData(%s) - %s", test.name, err.Error())
		return
	}
	if string(minified) != string(test.after) {
		t.Errorf("minifyPlayerData(%s) = '%s' != '%s'", test.name, minified, test.after)
		return
	}
}

func TestMinifyPlayerDataLiterals(t *testing.T) {
	for _, test := range literalTests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			if !test.error {
				var compacted bytes.Buffer
				err := json.Compact(&compacted, test.after)
				if err != nil {
					t.Errorf("minifyPlayerData(%s): Error compacting JSON: %s", test.name, err.Error())
					return
				}
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
	if err != nil {
		t.Errorf("Error reading fixtures directory: %s", err.Error())
		return
	}
	for _, file := range files {
		file := file
		if file.IsDir() {
			continue
		}
		t.Run(file.Name(), func(t *testing.T) {
			t.Parallel()
			filePath := path.Join(minifyFixtureDir, file.Name())
			test, err := parsePlayerDataFile(filePath)
			if err != nil {
				t.Errorf("Error parsing file %s: %s", filePath, err.Error())
			}
			// Real test
			runMinifyPlayerDataTest(t, test)

			// Test that minification is idempotent
			test.before = test.after
			test.name = test.name + " (minified)"
			runMinifyPlayerDataTest(t, test)
		})
	}
}
