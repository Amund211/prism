package app_test

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/adapters/uploadstore"
	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/domaintest"
)

const testUploadID = "0b5b8b8e-3a7e-4a57-9a3c-6f3c2a1d9e01"

var (
	startNow    = time.Date(2026, time.November, 7, 21, 30, 5, 0, time.UTC)
	completeNow = startNow.Add(2 * time.Minute)
	testUser    = domain.UploadIdentity{Type: domain.AuthSessionIdentityAnonymous, Key: "user-1"}
)

const (
	pendingPrefix = "tabcap/pending/" + testUploadID + "/"
	inboxPrefix   = "tabcap/inbox/2026-11-07/2026-11-07T213005Z_" + testUploadID + "/"
	filePrefix    = "2026-11-07T213005Z_0b5b8b8e_"
)

func newStartUpload(store app.UploadStore) app.StartUpload {
	return app.BuildStartUpload(store, func() string { return testUploadID }, func() time.Time { return startNow })
}

func newCompleteUpload(store app.UploadStore) app.CompleteUpload {
	return app.BuildCompleteUpload(store, func() time.Time { return completeNow })
}

func validStartRequest(files ...[]byte) app.StartUploadRequest {
	req := app.StartUploadRequest{
		Kind:           "tabcap",
		ConsentVersion: "2026-11-07",
		Fields: map[string]string{
			"launcher":     "lunar",
			"mcVersion":    "1.8.9",
			"resourcePack": " Default ",
			"guiScale":     "2",
		},
		Identity: testUser,
		Client:   domain.UploadClient{Type: "rainbow", Version: "evergreen"},
	}
	for i, data := range files {
		req.Files = append(req.Files, app.StartUploadFile{Name: []string{"a.png", `C:\Users\x\b.png`, "c.png"}[i%3], Bytes: int64(len(data))})
	}
	return req
}

// startAndPost starts an upload and posts each file as the client would.
func startAndPost(t *testing.T, store *uploadstore.MemoryStore, files ...[]byte) app.StartedUpload {
	t.Helper()
	started, err := newStartUpload(store)(t.Context(), validStartRequest(files...))
	require.NoError(t, err)
	for i, data := range files {
		require.NoError(t, store.ClientPost(started.Files[i], data))
	}
	return started
}

func TestStartUpload(t *testing.T) {
	t.Parallel()

	png := domaintest.NewPNG(2560, 1440, 8, 6, 100)

	t.Run("signs one post per file", func(t *testing.T) {
		t.Parallel()
		store := uploadstore.NewMemoryStore()
		started, err := newStartUpload(store)(t.Context(), validStartRequest(png, png))
		require.NoError(t, err)

		require.Equal(t, testUploadID, started.UploadID)
		require.True(t, started.ExpiresAt.Equal(startNow.Add(15*time.Minute)))
		require.Len(t, started.Files, 2)

		policies := store.Policies()
		require.Equal(t, uploadstore.Policy{ContentType: "image/png", Bytes: int64(len(png)), Expires: started.ExpiresAt}, policies[pendingPrefix+"1.png"])

		objects := store.Objects()
		require.Len(t, objects, 1, "only the pending state")
		require.Contains(t, objects, pendingPrefix+"upload.json")
	})

	t.Run("invalid requests sign nothing", func(t *testing.T) {
		t.Parallel()
		cases := map[string]func(*app.StartUploadRequest){
			"unknown kind":   func(r *app.StartUploadRequest) { r.Kind = "debuglog" },
			"invalid fields": func(r *app.StartUploadRequest) { r.Fields["guiScale"] = "9" },
			"no consent":     func(r *app.StartUploadRequest) { r.ConsentVersion = "" },
			"bad consent":    func(r *app.StartUploadRequest) { r.ConsentVersion = "yes" },
			"no identity":    func(r *app.StartUploadRequest) { r.Identity = domain.UploadIdentity{} },
			"no files":       func(r *app.StartUploadRequest) { r.Files = nil },
			"empty file":     func(r *app.StartUploadRequest) { r.Files[0].Bytes = 0 },
			"too many files": func(r *app.StartUploadRequest) { r.Files = make([]app.StartUploadFile, 31) },
			"negative size":  func(r *app.StartUploadRequest) { r.Files[0].Bytes = -1 },
		}
		for name, mutate := range cases {
			t.Run(name, func(t *testing.T) {
				t.Parallel()
				store := uploadstore.NewMemoryStore()
				req := validStartRequest(png)
				mutate(&req)
				_, err := newStartUpload(store)(t.Context(), req)
				require.ErrorIs(t, err, domain.ErrInvalidUpload)
				require.Empty(t, store.Objects())
				require.Empty(t, store.Policies())
			})
		}
	})

	t.Run("file too large", func(t *testing.T) {
		t.Parallel()
		req := validStartRequest(png)
		req.Files[0].Bytes = 10<<20 + 1
		_, err := newStartUpload(uploadstore.NewMemoryStore())(t.Context(), req)
		require.ErrorIs(t, err, domain.ErrUploadTooLarge)
		require.ErrorContains(t, err, "a.png")
	})

	t.Run("total too large", func(t *testing.T) {
		t.Parallel()
		req := validStartRequest()
		for range 21 {
			req.Files = append(req.Files, app.StartUploadFile{Name: "x.png", Bytes: 10 << 20})
		}
		_, err := newStartUpload(uploadstore.NewMemoryStore())(t.Context(), req)
		require.ErrorIs(t, err, domain.ErrUploadTooLarge)
	})

	t.Run("store error", func(t *testing.T) {
		t.Parallel()
		store := uploadstore.NewMemoryStore()
		store.FailWith(errors.New("gcs down"))
		_, err := newStartUpload(store)(t.Context(), validStartRequest(png))
		require.Error(t, err)
		require.NotErrorIs(t, err, domain.ErrInvalidUpload)
	})
}

func TestCompleteUpload(t *testing.T) {
	t.Parallel()

	png0 := domaintest.NewPNG(2560, 1440, 8, 6, 100)
	png1 := domaintest.NewPNG(1920, 1080, 8, 2, 10)

	t.Run("moves files to the inbox and writes meta last", func(t *testing.T) {
		t.Parallel()
		store := uploadstore.NewMemoryStore()
		startAndPost(t, store, png0, png1)

		id, err := newCompleteUpload(store)(t.Context(), "tabcap", testUploadID, testUser)
		require.NoError(t, err)
		require.Equal(t, testUploadID, id)

		objects := store.Objects()
		require.Len(t, objects, 3, "pending objects are deleted")
		require.Equal(t, png0, objects[inboxPrefix+filePrefix+"01.png"].Data)
		require.Equal(t, png1, objects[inboxPrefix+filePrefix+"02.png"].Data)
		require.Equal(t, "image/png", objects[inboxPrefix+filePrefix+"02.png"].ContentType)

		metaObject := objects[inboxPrefix+"meta.json"]
		require.Equal(t, "application/json", metaObject.ContentType)
		var meta domain.UploadMeta
		require.NoError(t, json.Unmarshal(metaObject.Data, &meta))

		require.Equal(t, testUploadID, meta.UploadID)
		require.Equal(t, domain.UploadKindTabcap, meta.Kind)
		require.Equal(t, 1, meta.SchemaVersion)
		require.True(t, meta.StartedAt.Equal(startNow))
		require.True(t, meta.CompletedAt.Equal(completeNow))
		require.Equal(t, "2026-11-07", meta.ConsentVersion)
		require.Equal(t, "user-submitted", meta.Provenance)
		require.False(t, meta.Verified)
		require.Equal(t, testUser, meta.Identity)
		require.Equal(t, domain.UploadClient{Type: "rainbow", Version: "evergreen"}, meta.Client)
		require.Equal(t, map[string]string{
			"launcher": "lunar", "mcVersion": "1.8.9", "resourcePack": "Default", "guiScale": "2",
		}, meta.UserReported)

		require.Equal(t, []domain.UploadedFile{
			{
				Name: filePrefix + "01.png", OriginalName: "a.png", Bytes: int64(len(png0)),
				MD5: uploadstore.MD5Hex(png0), Width: 2560, Height: 1440, ColorType: "rgba", BitDepth: 8,
			},
			{
				Name: filePrefix + "02.png", OriginalName: "b.png", Bytes: int64(len(png1)),
				MD5: uploadstore.MD5Hex(png1), Width: 1920, Height: 1080, ColorType: "rgb", BitDepth: 8,
			},
		}, meta.Files)
	})

	t.Run("second complete is not found", func(t *testing.T) {
		t.Parallel()
		store := uploadstore.NewMemoryStore()
		startAndPost(t, store, png0)
		complete := newCompleteUpload(store)
		_, err := complete(t.Context(), "tabcap", testUploadID, testUser)
		require.NoError(t, err)
		_, err = complete(t.Context(), "tabcap", testUploadID, testUser)
		require.ErrorIs(t, err, app.ErrUploadNotFound)
	})

	notFound := map[string]func() (string, string, domain.UploadIdentity){
		"unknown id": func() (string, string, domain.UploadIdentity) {
			return "tabcap", "6d2f4b1e-8c3a-4f5e-9b7d-1a2b3c4d5e6f", testUser
		},
		"not a uuid":   func() (string, string, domain.UploadIdentity) { return "tabcap", "../" + testUploadID, testUser },
		"unknown kind": func() (string, string, domain.UploadIdentity) { return "debuglog", testUploadID, testUser },
		"other identity": func() (string, string, domain.UploadIdentity) {
			return "tabcap", testUploadID, domain.UploadIdentity{Type: "anonymous", Key: "user-2"}
		},
	}
	for name, args := range notFound {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			store := uploadstore.NewMemoryStore()
			startAndPost(t, store, png0)
			kind, id, identity := args()
			_, err := newCompleteUpload(store)(t.Context(), kind, id, identity)
			require.ErrorIs(t, err, app.ErrUploadNotFound)
			require.Contains(t, store.Objects(), pendingPrefix+"upload.json", "nothing is deleted")
		})
	}

	t.Run("retry after meta.json is written succeeds", func(t *testing.T) {
		t.Parallel()
		store := uploadstore.NewMemoryStore()
		startAndPost(t, store, png0)
		// The first complete writes meta.json but cannot clean up pending.
		store.FailDeletes(true)
		complete := newCompleteUpload(store)
		_, err := complete(t.Context(), "tabcap", testUploadID, testUser)
		require.NoError(t, err)
		meta := store.Objects()[inboxPrefix+"meta.json"].Data

		store.FailDeletes(false)
		id, err := complete(t.Context(), "tabcap", testUploadID, testUser)
		require.NoError(t, err)
		require.Equal(t, testUploadID, id)
		require.Equal(t, meta, store.Objects()[inboxPrefix+"meta.json"].Data, "meta.json is kept")
		require.NotContains(t, store.Objects(), pendingPrefix+"upload.json", "pending is cleaned up")
	})

	t.Run("a concurrent complete that wrote meta.json first", func(t *testing.T) {
		t.Parallel()
		store := uploadstore.NewMemoryStore()
		startAndPost(t, store, png0)
		store.BeforeCopy(func() {
			require.NoError(t, store.Put(t.Context(), inboxPrefix+"meta.json", "application/json", []byte("{}")))
		})
		id, err := newCompleteUpload(store)(t.Context(), "tabcap", testUploadID, testUser)
		require.NoError(t, err)
		require.Equal(t, testUploadID, id)
	})

	t.Run("cleans up when the request is cancelled", func(t *testing.T) {
		t.Parallel()
		store := uploadstore.NewMemoryStore()
		startAndPost(t, store, png0)
		ctx, cancel := context.WithCancel(t.Context())
		// The client disconnects after meta.json is written.
		store.BeforeDelete(cancel)
		_, err := newCompleteUpload(store)(ctx, "tabcap", testUploadID, testUser)
		require.NoError(t, err)
		require.NotContains(t, store.Objects(), pendingPrefix+"upload.json")
	})

	t.Run("a file that is not uploaded yet keeps the upload", func(t *testing.T) {
		t.Parallel()
		store := uploadstore.NewMemoryStore()
		started, err := newStartUpload(store)(t.Context(), validStartRequest(png0, png1))
		require.NoError(t, err)
		require.NoError(t, store.ClientPost(started.Files[0], png0))

		complete := newCompleteUpload(store)
		_, err = complete(t.Context(), "tabcap", testUploadID, testUser)
		require.ErrorIs(t, err, app.ErrUploadIncomplete)
		require.EqualError(t, err, "b.png: upload is not complete: file was not uploaded")
		require.Contains(t, store.Objects(), pendingPrefix+"upload.json")
		require.Contains(t, store.Objects(), pendingPrefix+"0.png")

		require.NoError(t, store.ClientPost(started.Files[1], png1))
		_, err = complete(t.Context(), "tabcap", testUploadID, testUser)
		require.NoError(t, err)
	})

	t.Run("a file posted again during the check", func(t *testing.T) {
		t.Parallel()
		store := uploadstore.NewMemoryStore()
		started := startAndPost(t, store, png0)
		store.BeforeCopy(func() {
			_ = store.ClientPost(started.Files[0], png0)
		})
		complete := newCompleteUpload(store)
		_, err := complete(t.Context(), "tabcap", testUploadID, testUser)
		require.ErrorIs(t, err, app.ErrUploadIncomplete)
		require.EqualError(t, err, "a.png: upload is not complete: file changed during the check")
		require.NotContains(t, store.Objects(), inboxPrefix+"meta.json")

		_, err = complete(t.Context(), "tabcap", testUploadID, testUser)
		require.NoError(t, err, "a retry checks the new file")
	})

	badFiles := map[string]struct {
		post  func(t *testing.T, store *uploadstore.MemoryStore, started app.StartedUpload)
		cause string
	}{
		"not a png": {
			post: func(t *testing.T, store *uploadstore.MemoryStore, started app.StartedUpload) {
				require.NoError(t, store.ClientPost(started.Files[0], png0))
				require.NoError(t, store.ClientPost(started.Files[1], []byte(strings.Repeat("x", len(png1)))))
			},
			cause: "b.png: invalid upload: file is not a PNG",
		},
	}
	for name, tc := range badFiles {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			store := uploadstore.NewMemoryStore()
			started, err := newStartUpload(store)(t.Context(), validStartRequest(png0, png1))
			require.NoError(t, err)
			tc.post(t, store, started)

			_, err = newCompleteUpload(store)(t.Context(), "tabcap", testUploadID, testUser)
			require.ErrorIs(t, err, domain.ErrInvalidUpload)
			require.EqualError(t, err, tc.cause)
			require.Empty(t, store.Objects(), "a rejected upload is deleted")
		})
	}

	t.Run("store error", func(t *testing.T) {
		t.Parallel()
		store := uploadstore.NewMemoryStore()
		startAndPost(t, store, png0)
		store.FailWith(errors.New("gcs down"))
		_, err := newCompleteUpload(store)(t.Context(), "tabcap", testUploadID, testUser)
		require.Error(t, err)
		require.NotErrorIs(t, err, domain.ErrInvalidUpload)
		require.NotErrorIs(t, err, app.ErrUploadNotFound)
	})
}
