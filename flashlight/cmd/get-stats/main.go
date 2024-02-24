package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
)

type MojangResponse struct {
	Id   string `json:"id"`
	Name string `json:"name"`
}

func makeRequest(httpClient *http.Client, url string, apiKey string) ([]byte, int, error) {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		log.Println(err)
		return []byte{}, -1, fmt.Errorf("Constructing request: %w", err)
	}

	if apiKey != "" {
		req.Header.Set("API-Key", apiKey)
	}

	resp, err := httpClient.Do(req)
	if err != nil {
		log.Println(err)
		return []byte{}, -1, fmt.Errorf("Making request: %w", err)
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
	hypixelApiKey := os.Getenv("HYPIXEL_API_KEY")

	if hypixelApiKey == "" {
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

	if len(player) < 20 {
		// Player name -> ask mojang for uuid
		mojangUrl := fmt.Sprintf("https://api.mojang.com/users/profiles/minecraft/%s", player)
		data, statusCode, err := makeRequest(httpClient, mojangUrl, "")

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

		player = mojangResponse.Id
	}

	hypixelUrl := fmt.Sprintf("https://api.hypixel.net/player?uuid=%s", player)
	data, statusCode, err := makeRequest(httpClient, hypixelUrl, hypixelApiKey)
	if err != nil {
		log.Fatalf("Failed making request to Hypixel API: %v", err)
	}

	if statusCode != 200 {
		log.Printf("Hypixel API returned non-200 status code: %d - %s\n", statusCode, string(data))
	}

	fmt.Println(string(data))
	fmt.Println(statusCode)
}
