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
	"github.com/Amund211/flashlight/internal/strutils"
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

		parsedAPIResponse, err := playerprovider.ParseHypixelAPIResponse(context.Background(), hypixelAPIResponse)
		if err != nil {
			log.Printf("Error initially parsing hypixel api response %s: %s", fileName, err.Error())
			continue
		}

		uuid := "12345678-1234-1234-1234-12345678abcd"
		if parsedAPIResponse.Player != nil && parsedAPIResponse.Player.UUID != nil {
			normalizedUUID, err := strutils.NormalizeUUID(*parsedAPIResponse.Player.UUID)
			if err != nil {
				log.Fatalf("Error normalizing UUID: %s", err.Error())
			}
			uuid = normalizedUUID
		}

		player, err := playerprovider.HypixelAPIResponseToPlayerPIT(context.Background(), uuid, time.Now(), hypixelAPIResponse, 200)
		if err != nil {
			log.Printf("Error parsing hypixel api response %s: %s", fileName, err.Error())
			continue
		}

		apiResponseFromDomain := playerprovider.DomainPlayerToHypixelAPIResponse(player)

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
			err := os.WriteFile(expectedMinifiedDataPath, indentedBytes, 0644)
			if err != nil {
				log.Fatalf("Error writing expected minified data to %s: %s", expectedMinifiedDataPath, err.Error())
			}
		}
	}
}
