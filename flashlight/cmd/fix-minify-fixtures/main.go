package main

import (
	"bytes"
	"context"
	"log"
	"os"
	"path"

	"github.com/Amund211/flashlight/internal/processing"
)

const hypixelAPIResponsesDir = "./fixtures/hypixel_api_responses/"
const expectedMinifiedDataDir = "./internal/processing/testdata/expected_minified_data/"

func main() {
	hypixelAPIResponseFiles, err := os.ReadDir(hypixelAPIResponsesDir)
	if err != nil {
		log.Fatalf("Error reading hypixel api responses directory: %s", err.Error())
	}

	for _, hypixelAPIResponseFile := range hypixelAPIResponseFiles {
		if hypixelAPIResponseFile.IsDir() {
			continue
		}
		fileName := hypixelAPIResponseFile.Name()
		hypixelAPIResponse, err := os.ReadFile(path.Join(hypixelAPIResponsesDir, fileName))
		if err != nil {
			log.Printf("Error reading hypixel api response file %s: %s", fileName, err.Error())
			continue
		}
		expectedMinifiedDataPath := path.Join(expectedMinifiedDataDir, fileName)
		expectedMinifiedData, err := os.ReadFile(expectedMinifiedDataPath)
		if err != nil {
			expectedMinifiedData = nil
		}

		parsedAPIResponse, _, err := processing.ParseHypixelAPIResponse(context.Background(), hypixelAPIResponse, 200)
		newMinified, err := processing.MarshalPlayerData(context.Background(), parsedAPIResponse)
		if err != nil {
			log.Printf("Error minifying player data: %s", err.Error())
			continue
		}

		if !bytes.Equal(newMinified, expectedMinifiedData) {
			log.Printf("Updating fixture %s", fileName)
			os.WriteFile(expectedMinifiedDataPath, newMinified, 0644)
		}
	}
}
