package ports_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/adapters/uploadstore"
	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/domaintest"
	"github.com/Amund211/flashlight/internal/ports"
)

const uploadsTestID = "0b5b8b8e-3a7e-4a57-9a3c-6f3c2a1d9e01"

var uploadsTestNow = time.Date(2026, time.November, 7, 21, 30, 0, 0, time.UTC)

func uploadsBearerMiddleware(key string) func(http.HandlerFunc) http.HandlerFunc {
	return ports.NewBearerAuthMiddleware(
		func(ctx context.Context, sessionID string) (domain.AuthSession, error) {
			return domain.AuthSession{
				ID:           sessionID,
				IdentityType: domain.AuthSessionIdentityAnonymous,
				IdentityKey:  key,
				ExpiresAt:    time.Now().Add(time.Hour),
			}, nil
		},
		time.Now,
		ports.BlocklistConfig{},
	)
}

type uploadsHandlers struct {
	start    http.HandlerFunc
	complete http.HandlerFunc
}

func newUploadsHandlers(t *testing.T, store app.UploadStore, identityKey string) uploadsHandlers {
	t.Helper()
	startUpload := app.BuildStartUpload(store, func() string { return uploadsTestID }, func() time.Time { return uploadsTestNow })
	completeUpload := app.BuildCompleteUpload(store, func() time.Time { return uploadsTestNow.Add(time.Minute) })
	start, stopStart := ports.MakeStartUploadHandler(
		startUpload, authTestOrigins(t), authTestLogger, noopAuthMiddleware,
		uploadsBearerMiddleware(identityKey), emptyBlocklistConfig,
	)
	t.Cleanup(stopStart)
	complete, stopComplete := ports.MakeCompleteUploadHandler(
		completeUpload, authTestOrigins(t), authTestLogger, noopAuthMiddleware,
		uploadsBearerMiddleware(identityKey), emptyBlocklistConfig,
	)
	t.Cleanup(stopComplete)
	return uploadsHandlers{start: start, complete: complete}
}

func validStartBody(files ...[]byte) map[string]any {
	list := []map[string]any{}
	for i, data := range files {
		list = append(list, map[string]any{"name": []string{"a.png", "b.png"}[i%2], "bytes": len(data)})
	}
	return map[string]any{
		"consentVersion": "2026-11-07",
		"fields": map[string]string{
			"launcher":     "official",
			"mcVersion":    "1.8.9",
			"resourcePack": "none",
			"guiScale":     "auto",
		},
		"files": list,
	}
}

func newUploadsRequest(t *testing.T, target string, bearer bool, body []byte) *http.Request {
	t.Helper()
	req := httptest.NewRequestWithContext(t.Context(), http.MethodPost, target, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Origin", "https://example.com")
	req.Header.Set("X-Client-Type", "rainbow")
	req.Header.Set("X-Client-Version", "evergreen")
	if bearer {
		req.Header.Set("Authorization", "Bearer flsess_test")
	}
	return req
}

func newStartRequest(t *testing.T, kind string, bearer bool, body any) *http.Request {
	t.Helper()
	data, err := json.Marshal(body)
	require.NoError(t, err)
	req := newUploadsRequest(t, "/v1/uploads/"+kind, bearer, data)
	req.SetPathValue("kind", kind)
	return req
}

func newCompleteRequest(t *testing.T, kind, id string) *http.Request {
	t.Helper()
	req := newUploadsRequest(t, "/v1/uploads/"+kind+"/"+id+"/complete", true, nil)
	req.SetPathValue("kind", kind)
	req.SetPathValue("uploadId", id)
	return req
}

type uploadResponse struct {
	Success   bool                   `json:"success"`
	UploadID  string                 `json:"uploadId"`
	ExpiresAt time.Time              `json:"expiresAt"`
	Files     []app.UploadPostTarget `json:"files"`
	Cause     string                 `json:"cause"`
}

func doUploads(t *testing.T, handler http.HandlerFunc, req *http.Request) (int, uploadResponse) {
	t.Helper()
	w := httptest.NewRecorder()
	handler(w, req)
	resp := w.Result()
	require.Equal(t, "application/json", resp.Header.Get("Content-Type"))
	require.Equal(t, "https://example.com", resp.Header.Get("Access-Control-Allow-Origin"))
	// The start response holds signed policies.
	require.Equal(t, "no-store", resp.Header.Get("Cache-Control"))
	var body uploadResponse
	require.NoError(t, json.NewDecoder(resp.Body).Decode(&body))
	return resp.StatusCode, body
}

func TestUploadsHandlers(t *testing.T) {
	t.Parallel()

	png := domaintest.NewPNG(2560, 1440, 8, 6, 100)

	t.Run("start, post, complete", func(t *testing.T) {
		t.Parallel()
		store := uploadstore.NewMemoryStore()
		h := newUploadsHandlers(t, store, "user-1")

		status, started := doUploads(t, h.start, newStartRequest(t, "tabcap", true, validStartBody(png, png)))
		require.Equal(t, http.StatusCreated, status)
		require.True(t, started.Success)
		require.Equal(t, uploadsTestID, started.UploadID)
		require.True(t, started.ExpiresAt.Equal(uploadsTestNow.Add(15*time.Minute)))
		require.Len(t, started.Files, 2)

		for _, target := range started.Files {
			require.NoError(t, store.ClientPost(target, png))
		}

		status, completed := doUploads(t, h.complete, newCompleteRequest(t, "tabcap", uploadsTestID))
		require.Equal(t, http.StatusOK, status)
		require.Equal(t, uploadResponse{Success: true, UploadID: uploadsTestID}, completed)

		prefix := "tabcap/inbox/2026-11-07/2026-11-07T213000Z_" + uploadsTestID + "/"
		objects := store.Objects()
		require.Len(t, objects, 3)
		var meta domain.UploadMeta
		require.NoError(t, json.Unmarshal(objects[prefix+"meta.json"].Data, &meta))
		require.Equal(t, domain.UploadIdentity{Type: domain.AuthSessionIdentityAnonymous, Key: "user-1"}, meta.Identity)
		require.Equal(t, domain.UploadClient{Type: "rainbow", Version: "evergreen"}, meta.Client)
		require.Equal(t, "official", meta.UserReported["launcher"])
	})

	t.Run("start requires a bearer", func(t *testing.T) {
		t.Parallel()
		store := uploadstore.NewMemoryStore()
		status, body := doUploads(t, newUploadsHandlers(t, store, "user-1").start, newStartRequest(t, "tabcap", false, validStartBody(png)))
		require.Equal(t, http.StatusUnauthorized, status)
		require.False(t, body.Success)
		require.Empty(t, store.Objects())
	})

	t.Run("complete requires a bearer", func(t *testing.T) {
		t.Parallel()
		req := newCompleteRequest(t, "tabcap", uploadsTestID)
		req.Header.Del("Authorization")
		status, _ := doUploads(t, newUploadsHandlers(t, uploadstore.NewMemoryStore(), "user-1").complete, req)
		require.Equal(t, http.StatusUnauthorized, status)
	})

	t.Run("start rejects", func(t *testing.T) {
		t.Parallel()
		cases := map[string]struct {
			kind   string
			body   func() any
			status int
			cause  string
		}{
			"not json":       {"tabcap", func() any { return "{" }, http.StatusBadRequest, "body is not valid JSON"},
			"unknown kind":   {"debuglog", func() any { return validStartBody(png) }, http.StatusBadRequest, "invalid upload: unknown kind"},
			"invalid fields": {"tabcap", func() any { b := validStartBody(png); b["fields"].(map[string]string)["guiScale"] = "9"; return b }, http.StatusBadRequest, "invalid upload: guiScale has an unknown value"},
			"no files":       {"tabcap", func() any { return validStartBody() }, http.StatusBadRequest, "invalid upload: no files"},
			"file too large": {"tabcap", func() any {
				b := validStartBody(png)
				b["files"] = []map[string]any{{"name": "big.png", "bytes": 10<<20 + 1}}
				return b
			}, http.StatusRequestEntityTooLarge, "big.png: upload too large: file is larger than 10 MB"},
			"body too large": {"tabcap", func() any { b := validStartBody(png); b["pad"] = strings.Repeat("x", 70<<10); return b }, http.StatusRequestEntityTooLarge, "request is too large"},
		}
		for name, tc := range cases {
			t.Run(name, func(t *testing.T) {
				t.Parallel()
				store := uploadstore.NewMemoryStore()
				status, body := doUploads(t, newUploadsHandlers(t, store, "user-1").start, newStartRequest(t, tc.kind, true, tc.body()))
				require.Equal(t, tc.status, status)
				require.False(t, body.Success)
				require.Equal(t, tc.cause, body.Cause)
				require.Empty(t, store.Objects())
			})
		}
	})

	t.Run("complete of an unknown upload", func(t *testing.T) {
		t.Parallel()
		status, body := doUploads(t, newUploadsHandlers(t, uploadstore.NewMemoryStore(), "user-1").complete, newCompleteRequest(t, "tabcap", uploadsTestID))
		require.Equal(t, http.StatusNotFound, status)
		require.Equal(t, "upload not found", body.Cause)
	})

	t.Run("complete by someone else", func(t *testing.T) {
		t.Parallel()
		store := uploadstore.NewMemoryStore()
		started := doStartAndPost(t, newUploadsHandlers(t, store, "user-1"), store, png)
		require.Equal(t, uploadsTestID, started.UploadID)
		status, _ := doUploads(t, newUploadsHandlers(t, store, "user-2").complete, newCompleteRequest(t, "tabcap", uploadsTestID))
		require.Equal(t, http.StatusNotFound, status)
	})

	t.Run("complete before every file is posted", func(t *testing.T) {
		t.Parallel()
		store := uploadstore.NewMemoryStore()
		h := newUploadsHandlers(t, store, "user-1")
		_, started := doUploads(t, h.start, newStartRequest(t, "tabcap", true, validStartBody(png, png)))
		require.NoError(t, store.ClientPost(started.Files[0], png))
		status, body := doUploads(t, h.complete, newCompleteRequest(t, "tabcap", uploadsTestID))
		require.Equal(t, http.StatusConflict, status)
		require.Equal(t, "b.png: upload is not complete: file was not uploaded", body.Cause)
	})

	t.Run("complete with a bad file names it", func(t *testing.T) {
		t.Parallel()
		store := uploadstore.NewMemoryStore()
		h := newUploadsHandlers(t, store, "user-1")
		_, started := doUploads(t, h.start, newStartRequest(t, "tabcap", true, validStartBody(png)))
		require.NoError(t, store.ClientPost(started.Files[0], bytes.Repeat([]byte("x"), len(png))))
		status, body := doUploads(t, h.complete, newCompleteRequest(t, "tabcap", uploadsTestID))
		require.Equal(t, http.StatusBadRequest, status)
		require.Equal(t, "a.png: invalid upload: file is not a PNG", body.Cause)
	})

	t.Run("store failure", func(t *testing.T) {
		t.Parallel()
		store := uploadstore.NewMemoryStore()
		store.FailWith(errors.New("gcs down"))
		status, body := doUploads(t, newUploadsHandlers(t, store, "user-1").start, newStartRequest(t, "tabcap", true, validStartBody(png)))
		require.Equal(t, http.StatusInternalServerError, status)
		require.NotContains(t, body.Cause, "gcs")
	})
}

func doStartAndPost(t *testing.T, h uploadsHandlers, store *uploadstore.MemoryStore, files ...[]byte) uploadResponse {
	t.Helper()
	status, started := doUploads(t, h.start, newStartRequest(t, "tabcap", true, validStartBody(files...)))
	require.Equal(t, http.StatusCreated, status)
	for i, target := range started.Files {
		require.NoError(t, store.ClientPost(target, files[i]))
	}
	return started
}
