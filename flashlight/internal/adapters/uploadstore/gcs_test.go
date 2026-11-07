package uploadstore_test

import (
	"bytes"
	"context"
	"errors"
	"io"
	"mime/multipart"
	"net/http"
	"os"
	"strings"
	"testing"
	"time"

	"cloud.google.com/go/storage"
	"github.com/google/uuid"
	"github.com/stretchr/testify/require"
	"google.golang.org/api/iterator"

	"github.com/Amund211/flashlight/internal/adapters/uploadstore"
	"github.com/Amund211/flashlight/internal/app"
)

// Runs against a real bucket, e.g. prism-overlay-user-uploads-test, with
// application default credentials. Skipped when the bucket is not set.
// FLASHLIGHT_TEST_UPLOADS_SIGNER names the service account to sign as; the
// credentials need iam.serviceAccounts.signBlob on it.
func TestGCSStore(t *testing.T) {
	bucket := os.Getenv("FLASHLIGHT_TEST_UPLOADS_BUCKET")
	if bucket == "" {
		t.Skip("FLASHLIGHT_TEST_UPLOADS_BUCKET not set")
	}

	// Not t.Context(): it is cancelled before the cleanup runs.
	client, err := storage.NewClient(context.Background())
	require.NoError(t, err)
	t.Cleanup(func() { _ = client.Close() })

	store := uploadstore.NewGCSStore(client, bucket, os.Getenv("FLASHLIGHT_TEST_UPLOADS_SIGNER"))
	prefix := "integration-test/" + uuid.NewString() + "/"
	t.Cleanup(func() {
		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()
		objects := client.Bucket(bucket).Objects(ctx, &storage.Query{Prefix: prefix})
		for {
			attrs, err := objects.Next()
			if errors.Is(err, iterator.Done) {
				return
			}
			if err != nil {
				t.Errorf("failed to list %s: %v", prefix, err)
				return
			}
			err = client.Bucket(bucket).Object(attrs.Name).Delete(ctx)
			if err != nil && !errors.Is(err, storage.ErrObjectNotExist) {
				t.Errorf("failed to delete %s: %v", attrs.Name, err)
			}
		}
	})

	t.Run("put, stat, read, copy, delete", func(t *testing.T) {
		require.NoError(t, store.Put(t.Context(), prefix+"ok.txt", "text/plain", []byte("hello")))
		require.ErrorIs(t, store.Put(t.Context(), prefix+"ok.txt", "text/plain", []byte("changed")), app.ErrUploadObjectExists)

		data, err := store.Get(t.Context(), prefix+"ok.txt")
		require.NoError(t, err)
		require.Equal(t, "hello", string(data))

		obj, err := store.Stat(t.Context(), prefix+"ok.txt")
		require.NoError(t, err)
		require.Equal(t, int64(5), obj.Bytes)
		require.Equal(t, uploadstore.MD5Hex([]byte("hello")), obj.MD5)

		head, err := store.ReadHead(t.Context(), prefix+"ok.txt", obj.Generation, 3)
		require.NoError(t, err)
		require.Equal(t, "hel", string(head))

		_, err = store.ReadHead(t.Context(), prefix+"ok.txt", obj.Generation+1, 3)
		require.ErrorIs(t, err, app.ErrUploadObjectChanged)
		require.ErrorIs(t, store.Copy(t.Context(), prefix+"ok.txt", obj.Generation+1, prefix+"copy.txt"), app.ErrUploadObjectChanged)
		require.NoError(t, store.Copy(t.Context(), prefix+"ok.txt", obj.Generation, prefix+"copy.txt"))
		data, err = store.Get(t.Context(), prefix+"copy.txt")
		require.NoError(t, err)
		require.Equal(t, "hello", string(data))

		require.NoError(t, store.Delete(t.Context(), prefix+"copy.txt"))
		require.NoError(t, store.Delete(t.Context(), prefix+"copy.txt"), "missing is fine")
		_, err = store.Stat(t.Context(), prefix+"copy.txt")
		require.ErrorIs(t, err, app.ErrUploadObjectNotFound)
		_, err = store.Get(t.Context(), prefix+"copy.txt")
		require.ErrorIs(t, err, app.ErrUploadObjectNotFound)
	})

	t.Run("signed post enforces size and content type", func(t *testing.T) {
		if os.Getenv("FLASHLIGHT_TEST_UPLOADS_SIGNER") == "" {
			t.Skip("FLASHLIGHT_TEST_UPLOADS_SIGNER not set")
		}
		target, err := store.SignPost(prefix+"posted.txt", "image/png", 5, time.Now().Add(5*time.Minute))
		require.NoError(t, err)

		post := func(contentType, body string) int {
			var buf bytes.Buffer
			mw := multipart.NewWriter(&buf)
			for k, v := range target.Fields {
				if k == "content-type" {
					v = contentType
				}
				require.NoError(t, mw.WriteField(k, v))
			}
			fw, err := mw.CreateFormFile("file", "x.png")
			require.NoError(t, err)
			_, err = fw.Write([]byte(body))
			require.NoError(t, err)
			require.NoError(t, mw.Close())

			req, err := http.NewRequestWithContext(t.Context(), http.MethodPost, target.URL, &buf)
			require.NoError(t, err)
			req.Header.Set("Content-Type", mw.FormDataContentType())
			resp, err := http.DefaultClient.Do(req)
			require.NoError(t, err)
			defer func() { _ = resp.Body.Close() }()
			_, _ = io.Copy(io.Discard, resp.Body)
			return resp.StatusCode
		}

		require.NotEqual(t, http.StatusNoContent, post("image/png", "toolong"), "wrong size")
		require.NotEqual(t, http.StatusNoContent, post("text/html", "hello"), "wrong type")
		require.Equal(t, http.StatusNoContent, post("image/png", "hello"))

		data, err := store.Get(t.Context(), prefix+"posted.txt")
		require.NoError(t, err)
		require.Equal(t, "hello", strings.TrimSpace(string(data)))
	})
}
