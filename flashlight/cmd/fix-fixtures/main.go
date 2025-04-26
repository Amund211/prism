package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"os"
	"path"
	"time"

	"github.com/Amund211/flashlight/internal/adapters/playerprovider"
	"github.com/Amund211/flashlight/internal/ports"
	"github.com/Amund211/flashlight/internal/strutils"
)

const hypixelAPIResponsesDir = "./fixtures/hypixel_api_responses/"
const expectedPlayersDir = "./internal/adapters/playerprovider/testdata/expected_players/"
const expectedHypixelStyleResponsesDir = "./internal/ports/testdata/expected_hypixel_style_responses/"

func getUUID(hypixelAPIResponse []byte) (string, error) {
	parsedAPIResponse, err := playerprovider.ParseHypixelAPIResponse(context.Background(), hypixelAPIResponse)
	if err != nil {
		return "", fmt.Errorf("error parsing hypixel api response: %w", err)
	}
	if parsedAPIResponse.Player != nil && parsedAPIResponse.Player.UUID != nil {
		normalizedUUID, err := strutils.NormalizeUUID(*parsedAPIResponse.Player.UUID)
		if err != nil {
			return "", fmt.Errorf("error normalizing UUID: %w", err)
		}
		return normalizedUUID, nil
	}

	// No UUID in the response -> use a dummy UUID
	return "12345678-1234-1234-1234-12345678abcd", nil
}

func indentAndWrite(data []byte, filePath string) error {
	expectedBytes, err := os.ReadFile(filePath)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			// File doesn't exist -> create it
			expectedBytes = nil
		} else {
			return fmt.Errorf("error reading from %s: %w", filePath, err)
		}
	}

	indentedDataBuffer := bytes.NewBuffer(nil)
	err = json.Indent(indentedDataBuffer, data, "", "  ")
	if err != nil {
		return fmt.Errorf("error indenting JSON: %w", err)
	}
	indentedBytes := indentedDataBuffer.Bytes()

	if !bytes.Equal(indentedBytes, expectedBytes) {
		log.Printf("Updating fixture %s", filePath)
		err := os.WriteFile(filePath, indentedBytes, 0644)
		if err != nil {
			return fmt.Errorf("error writing to %s: %w", filePath, err)
		}
	}

	return nil
}

func main() {
	hypixelAPIResponseFiles, err := os.ReadDir(hypixelAPIResponsesDir)
	if err != nil {
		log.Fatalf("Error reading hypixel api responses directory: %s", err.Error())
	}

	// Fixed queriedAt time for hypixel response -> player tests
	playerQueriedAt, err := time.Parse(time.RFC3339, "2021-11-25T23:33:47+01:00")
	if err != nil {
		log.Fatalf("Error parsing player queriedAt time: %s", err.Error())
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

		// Get player
		uuid, err := getUUID(hypixelAPIResponse)
		if err != nil {
			log.Printf("Error getting UUID from hypixel api response %s: %s", fileName, err.Error())
			continue
		}
		player, err := playerprovider.HypixelAPIResponseToPlayerPIT(context.Background(), uuid, time.Now(), hypixelAPIResponse, 200)
		if err != nil {
			log.Printf("Error parsing hypixel api response %s: %s", fileName, err.Error())
			continue
		}
		player.QueriedAt = playerQueriedAt

		// Fix expected players
		// JSON marshal using go defaults for field names so we don't have to manually write out these structs
		playerJSON, err := json.Marshal(player)
		if err != nil {
			log.Printf("Error marshaling player to JSON: %s", err.Error())
			continue
		}
		err = indentAndWrite(playerJSON, path.Join(expectedPlayersDir, fileName))
		if err != nil {
			log.Printf("Error indenting and writing player JSON: %s", err.Error())
			continue
		}

		// Fix expected hypixel style responses
		hypixelStyleResponse, err := ports.PlayerToHypixelAPIResponseData(player)
		if err != nil {
			log.Printf("Error converting player to hypixel style response: %s", err.Error())
			continue
		}
		err = indentAndWrite(hypixelStyleResponse, path.Join(expectedHypixelStyleResponsesDir, fileName))
		if err != nil {
			log.Printf("Error indenting and writing hypixel style response: %s", err.Error())
			continue
		}
	}
}
