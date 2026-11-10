package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
)

type MojangResponse struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

func makeRequest(ctx context.Context, httpClient *http.Client, url string, apiKey string) ([]byte, int, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", url, http.NoBody)
	if err != nil {
		log.Println(err)
		return []byte{}, -1, fmt.Errorf("constructing request: %w", err)
	}

	if apiKey != "" {
		req.Header.Set("API-Key", apiKey)
	}

	resp, err := httpClient.Do(req)
	if err != nil {
		log.Println(err)
		return []byte{}, -1, fmt.Errorf("making request: %w", err)
	}

	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		log.Println(err)
		return []byte{}, -1, fmt.Errorf("ReadAll: %w", err)
	}

	return data, resp.StatusCode, nil
}

func main() {
	hypixelAPIKey := os.Getenv("HYPIXEL_API_KEY")

	if hypixelAPIKey == "" {
		log.Fatal("No Hypixel API key provided")
	}

	if len(os.Args) < 2 {
		log.Fatal("No player name provided")
	}

	player := os.Args[1]

	if player == "" {
		log.Fatal("No player name provided")
	}

	httpClient := &http.Client{}
	ctx := context.Background()

	if len(player) < 20 {
		// Player name -> ask mojang for uuid
		mojangURL := fmt.Sprintf("https://api.mojang.com/users/profiles/minecraft/%s", player)
		data, statusCode, err := makeRequest(ctx, httpClient, mojangURL, "")

		if err != nil {
			log.Fatalf("Failed making request to Mojang API: %v", err)
		}

		if statusCode != 200 {
			log.Fatalf("Mojang API returned non-200 status code: %d - %s", statusCode, string(data))
		}

		var mojangResponse MojangResponse
		err = json.Unmarshal(data, &mojangResponse)
		if err != nil {
			log.Fatalf("Failed parsing Mojang response: %v", err)
		}

		player = mojangResponse.ID
	}

	hypixelURL := fmt.Sprintf("https://api.hypixel.net/v2/player?uuid=%s", player)
	data, statusCode, err := makeRequest(ctx, httpClient, hypixelURL, hypixelAPIKey)
	if err != nil {
		log.Fatalf("Failed making request to Hypixel API: %v", err)
	}

	if statusCode != 200 {
		log.Printf("Hypixel API returned non-200 status code: %d - %s\n", statusCode, string(data))
	}

	fmt.Println(string(data))
	fmt.Println(statusCode)
}
