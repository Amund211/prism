package ports

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"time"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/reporting"
)

const maxStartUploadBodyBytes = 64 << 10

func uploadsMiddleware(
	name string,
	allowedOrigins *DomainSuffixes,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
	bearerAuthMiddleware func(http.HandlerFunc) http.HandlerFunc,
	blocklistConfig BlocklistConfig,
) (func(http.HandlerFunc) http.HandlerFunc, func()) {
	rateLimit, stop := NewAuthRateLimitMiddleware(UploadsRateLimitPolicy, jsonRateLimitExceeded)
	return ComposeMiddlewares(
		NewRequestLoggerMiddleware(rootLogger),
		sentryMiddleware,
		BuildBlocklistMiddleware(blocklistConfig),
		buildMetricsMiddleware(name),
		NewReportingMetaMiddleware(name),
		BuildCORSMiddleware(allowedOrigins),
		bearerAuthMiddleware,
		rateLimit,
	), stop
}

// MakeStartUploadHandler serves POST /v1/uploads/{kind}. It checks the
// details and returns one signed POST per file, so the files go straight to
// the bucket.
func MakeStartUploadHandler(
	startUpload app.StartUpload,
	allowedOrigins *DomainSuffixes,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
	bearerAuthMiddleware func(http.HandlerFunc) http.HandlerFunc,
	blocklistConfig BlocklistConfig,
) (http.HandlerFunc, func()) {
	middleware, stop := uploadsMiddleware("uploads_start", allowedOrigins, rootLogger, sentryMiddleware, bearerAuthMiddleware, blocklistConfig)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		auth, ok := AuthFromContext(ctx)
		if !ok {
			writeUploadError(w, http.StatusUnauthorized, "sign-in required")
			return
		}

		raw, err := io.ReadAll(io.LimitReader(r.Body, maxStartUploadBodyBytes+1))
		if err != nil {
			writeUploadError(w, http.StatusBadRequest, "failed to read request")
			return
		}
		if len(raw) > maxStartUploadBodyBytes {
			writeUploadError(w, http.StatusRequestEntityTooLarge, "request is too large")
			return
		}
		var body struct {
			ConsentVersion string            `json:"consentVersion"`
			Fields         map[string]string `json:"fields"`
			Files          []struct {
				Name  string `json:"name"`
				Bytes int64  `json:"bytes"`
			} `json:"files"`
		}
		if err := json.Unmarshal(raw, &body); err != nil {
			writeUploadError(w, http.StatusBadRequest, "body is not valid JSON")
			return
		}

		files := make([]app.StartUploadFile, len(body.Files))
		for i, f := range body.Files {
			files[i] = app.StartUploadFile{Name: f.Name, Bytes: f.Bytes}
		}
		client := GetClient(r)
		started, err := startUpload(ctx, app.StartUploadRequest{
			Kind:           r.PathValue("kind"),
			ConsentVersion: body.ConsentVersion,
			Fields:         body.Fields,
			Files:          files,
			Identity:       domain.UploadIdentity{Type: auth.IdentityType, Key: auth.IdentityKey},
			Client:         domain.UploadClient{Type: client.Type, Version: client.Version},
		})
		if err != nil {
			writeUploadAppError(w, r, err)
			return
		}

		logging.FromContext(ctx).InfoContext(ctx, "Started upload", slog.String("uploadId", started.UploadID), slog.Int("files", len(files)))
		writeUploadJSON(w, http.StatusCreated, struct {
			Success   bool                   `json:"success"`
			UploadID  string                 `json:"uploadId"`
			ExpiresAt time.Time              `json:"expiresAt"`
			Files     []app.UploadPostTarget `json:"files"`
		}{true, started.UploadID, started.ExpiresAt, started.Files})
	}

	return middleware(handler), stop
}

// MakeCompleteUploadHandler serves POST /v1/uploads/{kind}/{uploadId}/complete.
// It checks the posted files and moves them to the inbox.
func MakeCompleteUploadHandler(
	completeUpload app.CompleteUpload,
	allowedOrigins *DomainSuffixes,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
	bearerAuthMiddleware func(http.HandlerFunc) http.HandlerFunc,
	blocklistConfig BlocklistConfig,
) (http.HandlerFunc, func()) {
	middleware, stop := uploadsMiddleware("uploads_complete", allowedOrigins, rootLogger, sentryMiddleware, bearerAuthMiddleware, blocklistConfig)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		auth, ok := AuthFromContext(ctx)
		if !ok {
			writeUploadError(w, http.StatusUnauthorized, "sign-in required")
			return
		}

		uploadID, err := completeUpload(ctx, r.PathValue("kind"), r.PathValue("uploadId"),
			domain.UploadIdentity{Type: auth.IdentityType, Key: auth.IdentityKey})
		if err != nil {
			writeUploadAppError(w, r, err)
			return
		}

		logging.FromContext(ctx).InfoContext(ctx, "Completed upload", slog.String("uploadId", uploadID))
		writeUploadJSON(w, http.StatusOK, struct {
			Success  bool   `json:"success"`
			UploadID string `json:"uploadId"`
		}{true, uploadID})
	}

	return middleware(handler), stop
}

func writeUploadAppError(w http.ResponseWriter, r *http.Request, err error) {
	switch {
	case errors.Is(err, domain.ErrUploadTooLarge):
		writeUploadError(w, http.StatusRequestEntityTooLarge, err.Error())
	case errors.Is(err, domain.ErrInvalidUpload):
		writeUploadError(w, http.StatusBadRequest, err.Error())
	case errors.Is(err, app.ErrUploadIncomplete):
		writeUploadError(w, http.StatusConflict, err.Error())
	case errors.Is(err, app.ErrUploadNotFound):
		writeUploadError(w, http.StatusNotFound, "upload not found")
	default:
		reporting.Report(r.Context(), fmt.Errorf("upload failed: %w", err))
		writeUploadError(w, http.StatusInternalServerError, "upload failed")
	}
}

func writeUploadJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	// The start response holds signed policies, which work as credentials.
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func writeUploadError(w http.ResponseWriter, status int, cause string) {
	writeUploadJSON(w, status, struct {
		Success bool   `json:"success"`
		Cause   string `json:"cause"`
	}{false, cause})
}
