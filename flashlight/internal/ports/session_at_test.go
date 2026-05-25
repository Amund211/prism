package ports_test

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/domaintest"
	"github.com/Amund211/flashlight/internal/ports"
)

func TestMakeGetSessionAtHandler(t *testing.T) {
	t.Parallel()

	allowedOrigins, err := ports.NewDomainSuffixes("example.com", "test.com")
	require.NoError(t, err)

	testLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	noopMiddleware := func(h http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			h(w, r)
		}
	}

	makeHandler := func(getSessionAt app.GetSessionAt) http.HandlerFunc {
		stubRegisterUserVisit := func(ctx context.Context, userID string, ipHash string, userAgent string) (domain.User, error) {
			return domain.User{}, nil
		}
		return ports.MakeGetSessionAtHandler(
			getSessionAt,
			stubRegisterUserVisit,
			allowedOrigins,
			testLogger,
			noopMiddleware,
			emptyBlocklistConfig,
		)
	}

	makeRequest := func(uuid, timeStr string) *http.Request {
		body := io.NopCloser(strings.NewReader(
			fmt.Sprintf(`{"uuid":"%s","time":"%s"}`, uuid, timeStr),
		))
		return httptest.NewRequestWithContext(t.Context(), "POST", "/session-at", body)
	}

	uuid := "01234567-89ab-cdef-0123-456789abcdef"
	at := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)

	type gameResponse struct {
		Gamemode   string `json:"gamemode"`
		Won        bool   `json:"won"`
		FinalKills int    `json:"finalKills"`
		FinalDeath bool   `json:"finalDeath"`
		BedsBroken int    `json:"bedsBroken"`
		BedLost    bool   `json:"bedLost"`
		Kills      int    `json:"kills"`
		Deaths     int    `json:"deaths"`
		Experience int64  `json:"experience"`
	}
	type segmentResponse struct {
		Start map[string]any `json:"start"`
		End   map[string]any `json:"end"`
		Game  *gameResponse  `json:"game"`
	}
	type sessionAtResponse struct {
		Session *struct {
			Start       map[string]any `json:"start"`
			End         map[string]any `json:"end"`
			Consecutive bool           `json:"consecutive"`
		} `json:"session"`
		Games []segmentResponse `json:"games"`
	}

	t.Run("forwards uuid and time to app method and renders games", func(t *testing.T) {
		t.Parallel()

		sessionStart := time.Date(2024, 1, 1, 11, 0, 0, 0, time.UTC)
		mid := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
		sessionEnd := time.Date(2024, 1, 1, 13, 0, 0, 0, time.UTC)

		startPIT := domaintest.NewPlayerBuilder(uuid).
			WithExperience(1000).FromDB().Fours().WithGamesPlayed(10).Build(sessionStart)
		midPIT := domaintest.NewPlayerBuilder(uuid).
			WithExperience(1500).FromDB().Fours().WithGamesPlayed(11).Build(mid)
		endPIT := domaintest.NewPlayerBuilder(uuid).
			WithExperience(2000).FromDB().Fours().WithGamesPlayed(12).Build(sessionEnd)

		result := app.SessionAtResult{
			Session: &domain.Session{
				Start:       startPIT,
				End:         endPIT,
				Consecutive: true,
			},
			Games: []app.GameSegment{
				{
					Start: startPIT,
					End:   midPIT,
					Game: &domain.GameResult{
						Gamemode:   domain.GamemodeDoubles,
						Won:        true,
						FinalKills: 4,
						FinalDeath: false,
						BedsBroken: 1,
						BedLost:    false,
						Kills:      8,
						Deaths:     2,
						Experience: 500,
					},
				},
				// Second segment has Game nil (ambiguous / heartbeat).
				{Start: midPIT, End: endPIT, Game: nil},
			},
		}

		called := false
		getSessionAt := func(ctx context.Context, gotUUID string, gotAt time.Time) (app.SessionAtResult, error) {
			called = true
			require.Equal(t, uuid, gotUUID)
			require.WithinDuration(t, at, gotAt, 0)
			return result, nil
		}

		handler := makeHandler(getSessionAt)
		req := makeRequest(uuid, at.Format(time.RFC3339))
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusOK, w.Code)
		require.True(t, called)

		var response sessionAtResponse
		require.NoError(t, json.Unmarshal(w.Body.Bytes(), &response))

		require.NotNil(t, response.Session)
		require.True(t, response.Session.Consecutive)
		require.Equal(t, sessionStart.Format(time.RFC3339), response.Session.Start["queriedAt"])
		require.Equal(t, sessionEnd.Format(time.RFC3339), response.Session.End["queriedAt"])

		require.Len(t, response.Games, 2)
		require.NotNil(t, response.Games[0].Game)
		require.Equal(t, "doubles", response.Games[0].Game.Gamemode)
		require.True(t, response.Games[0].Game.Won)
		require.Equal(t, 4, response.Games[0].Game.FinalKills)
		require.False(t, response.Games[0].Game.FinalDeath)
		require.Equal(t, 1, response.Games[0].Game.BedsBroken)
		require.False(t, response.Games[0].Game.BedLost)
		require.Equal(t, int64(500), response.Games[0].Game.Experience)
		require.Equal(t, sessionStart.Format(time.RFC3339), response.Games[0].Start["queriedAt"])
		require.Equal(t, mid.Format(time.RFC3339), response.Games[0].End["queriedAt"])

		// Second segment: Game is nil in JSON.
		require.Nil(t, response.Games[1].Game)
		require.Equal(t, mid.Format(time.RFC3339), response.Games[1].Start["queriedAt"])
		require.Equal(t, sessionEnd.Format(time.RFC3339), response.Games[1].End["queriedAt"])
	})

	t.Run("all four gamemodes serialise to their wire names", func(t *testing.T) {
		t.Parallel()

		startPIT := domaintest.NewPlayerBuilder(uuid).FromDB().Build(at)

		mkSegment := func(g domain.Gamemode) app.GameSegment {
			return app.GameSegment{
				Start: startPIT,
				End:   startPIT,
				Game:  &domain.GameResult{Gamemode: g, Won: true},
			}
		}

		result := app.SessionAtResult{
			Session: &domain.Session{Start: startPIT, End: startPIT, Consecutive: true},
			Games: []app.GameSegment{
				mkSegment(domain.GamemodeSolo),
				mkSegment(domain.GamemodeDoubles),
				mkSegment(domain.GamemodeThrees),
				mkSegment(domain.GamemodeFours),
			},
		}

		getSessionAt := func(ctx context.Context, _ string, _ time.Time) (app.SessionAtResult, error) {
			return result, nil
		}

		handler := makeHandler(getSessionAt)
		req := makeRequest(uuid, at.Format(time.RFC3339))
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusOK, w.Code)

		var response sessionAtResponse
		require.NoError(t, json.Unmarshal(w.Body.Bytes(), &response))
		require.Len(t, response.Games, 4)
		require.Equal(t, "solo", response.Games[0].Game.Gamemode)
		require.Equal(t, "doubles", response.Games[1].Game.Gamemode)
		require.Equal(t, "threes", response.Games[2].Game.Gamemode)
		require.Equal(t, "fours", response.Games[3].Game.Gamemode)
	})

	t.Run("unknown gamemode returns 500", func(t *testing.T) {
		t.Parallel()

		startPIT := domaintest.NewPlayerBuilder(uuid).FromDB().Build(at)

		result := app.SessionAtResult{
			Session: &domain.Session{Start: startPIT, End: startPIT, Consecutive: true},
			Games: []app.GameSegment{
				{
					Start: startPIT,
					End:   startPIT,
					Game:  &domain.GameResult{Gamemode: domain.Gamemode("bogus")},
				},
			},
		}

		getSessionAt := func(ctx context.Context, _ string, _ time.Time) (app.SessionAtResult, error) {
			return result, nil
		}

		handler := makeHandler(getSessionAt)
		req := makeRequest(uuid, at.Format(time.RFC3339))
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusInternalServerError, w.Code)
	})

	t.Run("nil session is rendered as null with empty games", func(t *testing.T) {
		t.Parallel()

		getSessionAt := func(ctx context.Context, gotUUID string, gotAt time.Time) (app.SessionAtResult, error) {
			return app.SessionAtResult{Session: nil, Games: nil}, nil
		}

		handler := makeHandler(getSessionAt)
		req := makeRequest(uuid, at.Format(time.RFC3339))
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusOK, w.Code)

		var response sessionAtResponse
		require.NoError(t, json.Unmarshal(w.Body.Bytes(), &response))
		require.Nil(t, response.Session)
		require.Empty(t, response.Games)
	})

	makeAssertNotCalled := func(t *testing.T) app.GetSessionAt {
		return func(ctx context.Context, uuid string, at time.Time) (app.SessionAtResult, error) {
			t.Helper()
			t.Fatal("getSessionAt should not be called")
			return app.SessionAtResult{}, nil
		}
	}

	t.Run("invalid UUID", func(t *testing.T) {
		t.Parallel()

		handler := makeHandler(makeAssertNotCalled(t))
		req := makeRequest("not-a-uuid", at.Format(time.RFC3339))
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusBadRequest, w.Code)
		require.Contains(t, w.Body.String(), "invalid uuid")
	})

	t.Run("missing time", func(t *testing.T) {
		t.Parallel()

		handler := makeHandler(makeAssertNotCalled(t))
		body := io.NopCloser(strings.NewReader(fmt.Sprintf(`{"uuid":"%s"}`, uuid)))
		req := httptest.NewRequestWithContext(t.Context(), "POST", "/session-at", body)
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusBadRequest, w.Code)
		require.Contains(t, w.Body.String(), "missing time")
	})

	t.Run("request body exceeds size limit", func(t *testing.T) {
		t.Parallel()

		handler := makeHandler(makeAssertNotCalled(t))
		// Build a body larger than the 4 KB limit by padding the UUID field.
		oversized := fmt.Sprintf(
			`{"uuid":"%s","time":"%s"}`,
			strings.Repeat("a", 5<<10),
			at.Format(time.RFC3339),
		)
		body := io.NopCloser(strings.NewReader(oversized))
		req := httptest.NewRequestWithContext(t.Context(), "POST", "/session-at", body)
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusRequestEntityTooLarge, w.Code)
	})

	t.Run("malformed JSON", func(t *testing.T) {
		t.Parallel()

		handler := makeHandler(makeAssertNotCalled(t))
		body := io.NopCloser(strings.NewReader("not json"))
		req := httptest.NewRequestWithContext(t.Context(), "POST", "/session-at", body)
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusBadRequest, w.Code)
	})

	t.Run("app method failure returns 500", func(t *testing.T) {
		t.Parallel()

		getSessionAt := func(ctx context.Context, uuid string, at time.Time) (app.SessionAtResult, error) {
			return app.SessionAtResult{}, fmt.Errorf("boom")
		}

		handler := makeHandler(getSessionAt)
		req := makeRequest(uuid, at.Format(time.RFC3339))
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, req)

		require.Equal(t, http.StatusInternalServerError, w.Code)
	})
}
