package main

import (
	"log"
	"net/http"
	"io/ioutil"
	"os"
	"errors"
	"fmt"

	"github.com/GoogleCloudPlatform/functions-framework-go/functions"
)

func getPlayerData(w http.ResponseWriter, r *http.Request) {
	log.Println("Got request")

	uuid := r.URL.Query().Get("uuid")
	apiKey := os.Getenv("HYPIXEL_API_KEY")

	if uuid == "" {
		log.Println("Missing uuid")
		return
	}

	s := fmt.Sprintf("https://api.hypixel.net/player?key=%s&uuid=%s", apiKey, uuid)

	resp, err := http.Get(s)
	if err != nil {
		log.Fatalln(err)
	}

	defer resp.Body.Close()
	data, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		log.Fatalln(err)
	}

	w.Header().Set("Content-Type", "application/json")
	w.Write(data)
}


func initsh() {
	log.Println("Starting server in init")

	functions.HTTP("laser", getPlayerData)
}

func main() {
	log.Println("Starting server")

	mux := http.NewServeMux()

	mux.HandleFunc("/", getPlayerData)

	err := http.ListenAndServe(":3000", mux)

	if errors.Is(err, http.ErrServerClosed) {
		log.Println("server closed")
	} else if err != nil {
		log.Printf("error starting server: %s\n", err)
		os.Exit(1)
	}
}
