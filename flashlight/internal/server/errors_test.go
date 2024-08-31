package server

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"reflect"
	"testing"

	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/stretchr/testify/assert"
)

func TestWriteErrorResponse(t *testing.T) {
	testCases := []struct {
		err            error
		expectedStatus int
		expectedBody   string
	}{
		{
			err:            e.APIServerError,
			expectedStatus: 500,
			expectedBody:   `{"success":false,"cause":"Server error"}`,
		},
		{
			err:            e.APIClientError,
			expectedStatus: 400,
			expectedBody:   `{"success":false,"cause":"Client error"}`,
		},
		{
			err:            e.RatelimitExceededError,
			expectedStatus: 429,
			expectedBody:   `{"success":false,"cause":"Ratelimit exceeded"}`,
		},
		{
			err:            fmt.Errorf("something happened %w", e.RetriableError),
			expectedStatus: 504,
			expectedBody:   `{"success":false,"cause":"something happened (retriable)"}`,
		},
		{
			err:            fmt.Errorf("%w %w", e.RatelimitExceededError, e.RetriableError),
			expectedStatus: 429,
			expectedBody:   `{"success":false,"cause":"Ratelimit exceeded (retriable)"}`,
		},
	}

	expectedHeaders := make(http.Header)
	expectedHeaders.Set("Content-Type", "application/json")

	for _, testCase := range testCases {
		w := httptest.NewRecorder()

		returnedStatusCode := writeErrorResponse(context.Background(), w, testCase.err)
		result := w.Result()

		assert.True(t, reflect.DeepEqual(expectedHeaders, result.Header), "Expected %v, got %v", expectedHeaders, result.Header)

		assert.Equal(t, testCase.expectedStatus, result.StatusCode)
		assert.Equal(t, testCase.expectedStatus, returnedStatusCode)

		body := w.Body.String()
		assert.Equal(t, testCase.expectedBody, body)
	}
}
