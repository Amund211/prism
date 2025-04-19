package main

import (
	"bytes"
	"context"
	"encoding/json"
	"log"
	"os"
	"path"
	"time"

	"github.com/Amund211/flashlight/internal/adapters/playerprovider"
)

const hypixelAPIResponsesDir = "./fixtures/hypixel_api_responses/"
const expectedMinifiedDataDir = "./internal/adapters/playerprovider/testdata/expected_minified_data/"

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

		parsedAPIResponse, _, err := playerprovider.ParseHypixelAPIResponse(context.Background(), hypixelAPIResponse, 200)
		if err != nil {
			log.Printf("Error parsing hypixel api response %s: %s", fileName, err.Error())
			continue
		}

		domainPlayer, err := playerprovider.HypixelAPIResponseToDomainPlayer(parsedAPIResponse, time.Now(), nil)
		if err != nil {
			log.Printf("Error converting hypixel api response to domain player %s: %s", fileName, err.Error())
			continue
		}

		apiResponseFromDomain := playerprovider.DomainPlayerToHypixelAPIResponse(domainPlayer)

		newMinified, err := playerprovider.MarshalPlayerData(context.Background(), apiResponseFromDomain)
		if err != nil {
			log.Printf("Error minifying player data: %s", err.Error())
			continue
		}

		indented := bytes.NewBuffer(nil)
		err = json.Indent(indented, newMinified, "", "  ")
		if err != nil {
			log.Fatalf("Error indenting JSON: %s", err.Error())
		}

		indentedBytes := indented.Bytes()

		if !bytes.Equal(indentedBytes, expectedMinifiedData) {
			log.Printf("Updating fixture %s", fileName)
			os.WriteFile(expectedMinifiedDataPath, indentedBytes, 0644)
		}
	}
}
