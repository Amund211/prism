package hypixel

import (
	"fmt"
	"io"
	"log"
	"net/http"

	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/Amund211/flashlight/internal/constants"
)

type HypixelAPI interface {
	GetPlayerData(uuid string) ([]byte, int, error)
}

type hypixelAPIImpl struct {
	httpClient *http.Client
	apiKey     string
}

func (hypixelAPI hypixelAPIImpl) GetPlayerData(uuid string) ([]byte, int, error) {
	url := fmt.Sprintf("https://api.hypixel.net/player?uuid=%s", uuid)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		log.Println(err)
		return []byte{}, -1, fmt.Errorf("%w: %w", e.APIServerError, err)
	}

	req.Header.Set("User-Agent", constants.USER_AGENT)
	req.Header.Set("API-Key", hypixelAPI.apiKey)

	resp, err := hypixelAPI.httpClient.Do(req)
	if err != nil {
		log.Println(err)
		return []byte{}, -1, fmt.Errorf("%w: %w", e.APIServerError, err)
	}

	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		log.Println(err)
		return []byte{}, -1, fmt.Errorf("%w: %w", e.APIServerError, err)
	}

	return data, resp.StatusCode, nil
}

func NewHypixelAPI(httpClient *http.Client, apiKey string) HypixelAPI {
	return hypixelAPIImpl{
		httpClient: httpClient,
		apiKey:     apiKey,
	}
}
