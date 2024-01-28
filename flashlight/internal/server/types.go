package server

import (
    "net/http"
)

type Handler func(w http.ResponseWriter, r *http.Request)

type HypixelAPIErrorResponse struct {
	Success bool   `json:"success"`
	Cause   string `json:"cause"`
}

