package proofofwork_test

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"math/bits"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/proofofwork"
)

const testIPHash = "0000000000000000000000000000000000000000000000000000000000000001"

const testUserID = "user-abc"

var errUnexpected = errors.New("something else entirely")

var testTime = time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC)

func testKey(t *testing.T, fill byte) []byte {
	t.Helper()
	key := make([]byte, 32)
	for i := range key {
		key[i] = fill
	}
	return key
}

// clock is a nowFunc whose value the test can move.
type clock struct{ now time.Time }

func (c *clock) Now() time.Time { return c.now }

func fixedDifficulty(difficulty int) proofofwork.DifficultyFunc {
	return func(proofofwork.DifficultyInput) int { return difficulty }
}

// solve brute-forces a solution the way a client would. Deliberately
// re-implements the leading-zero-bit count rather than reusing the
// package's, so the tests pin the definition of the algorithm and not just
// its self-consistency.
func solve(t *testing.T, challenge string, difficulty int) string {
	t.Helper()
	for attempt := range 1 << 22 {
		solution := strconv.Itoa(attempt)
		if solutionZeroBits(challenge, solution) >= difficulty {
			return solution
		}
	}
	t.Fatalf("no solution found for difficulty %d", difficulty)
	return ""
}

// solveShortOf finds a solution that clears atLeast zero bits but stays
// under below — a genuine proof of less work than was asked for. Searching
// for the bracket rather than just solving for the lower bar keeps the test
// deterministic: the first solution clearing (difficulty - 4) bits clears
// the real bar too about one run in sixteen.
func solveShortOf(t *testing.T, challenge string, atLeast int, below int) string {
	t.Helper()
	for attempt := range 1 << 22 {
		solution := strconv.Itoa(attempt)
		if zeros := solutionZeroBits(challenge, solution); zeros >= atLeast && zeros < below {
			return solution
		}
	}
	t.Fatalf("no solution found in [%d, %d) zero bits", atLeast, below)
	return ""
}

func solutionZeroBits(challenge, solution string) int {
	digest := sha256.Sum256([]byte(challenge + ":" + solution))
	zeros := 0
	for _, b := range digest {
		zeros += bits.LeadingZeros8(b)
		if b != 0 {
			break
		}
	}
	return zeros
}

// scheme wires both halves against one set of keys and one clock, which is
// how they are used in production. The verify it returns is parse-then-check
// the way the login handler runs them, for the cases that don't care which
// half refused; the ones that do build the halves themselves.
func scheme(t *testing.T, keys [][]byte, difficulty int, c *clock) (proofofwork.IssueChallenge, func(challenge, solution, userID, ipHash string) error) {
	t.Helper()
	issue, parse := parsingScheme(t, keys, difficulty, c)
	return issue, func(challenge, solution, userID, ipHash string) error {
		signed, err := parse(challenge)
		if err != nil {
			return err
		}
		return signed.Check(solution, userID, ipHash)
	}
}

func parsingScheme(t *testing.T, keys [][]byte, difficulty int, c *clock) (proofofwork.IssueChallenge, proofofwork.ParseChallenge) {
	t.Helper()
	issue, err := proofofwork.BuildIssueChallenge(keys, fixedDifficulty(difficulty), c.Now)
	require.NoError(t, err)
	parse, err := proofofwork.BuildParseChallenge(keys, c.Now)
	require.NoError(t, err)
	return issue, parse
}

// signPayload mints a challenge the way a different revision might have, so
// the tests pin what verification accepts and not only what this revision
// produces. Takes raw JSON for the same reason.
func signPayload(t *testing.T, key []byte, payloadJSON string) string {
	t.Helper()
	body := base64.RawURLEncoding.EncodeToString([]byte(payloadJSON))
	mac := hmac.New(sha256.New, key)
	_, err := mac.Write([]byte(body))
	require.NoError(t, err)
	return body + "." + base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}

func TestIssueAndVerify(t *testing.T) {
	t.Parallel()

	t.Run("a solved challenge verifies", func(t *testing.T) {
		t.Parallel()
		c := &clock{now: testTime}
		issue, verify := scheme(t, [][]byte{testKey(t, 1)}, 0, c)

		challenge, err := issue(testUserID, testIPHash, "prism")
		require.NoError(t, err)
		require.Equal(t, proofofwork.AlgorithmSHA256LeadingZeros, challenge.Algorithm)
		require.Equal(t, 0, challenge.Difficulty)
		require.Equal(t, 60*time.Second, challenge.ExpiresIn)
		require.NotEmpty(t, challenge.Value)

		require.NoError(t, verify(challenge.Value, solve(t, challenge.Value, 0), testUserID, testIPHash))
	})

	t.Run("difficulty travels inside the challenge", func(t *testing.T) {
		t.Parallel()
		const difficulty = 10
		c := &clock{now: testTime}
		issue, verify := scheme(t, [][]byte{testKey(t, 1)}, difficulty, c)

		challenge, err := issue(testUserID, testIPHash, "prism")
		require.NoError(t, err)
		require.Equal(t, difficulty, challenge.Difficulty)

		// A solution that only clears a lower bar is not enough, even
		// though verification was never told what difficulty was asked for.
		tooEasy := solveShortOf(t, challenge.Value, difficulty-4, difficulty)
		require.GreaterOrEqual(t, solutionZeroBits(challenge.Value, tooEasy), difficulty-4,
			"the rejected solution should be real work, just not enough of it")
		require.ErrorIs(t, verify(challenge.Value, tooEasy, testUserID, testIPHash), proofofwork.ErrInsufficientWork)

		// ...and a fresh challenge solved properly is.
		challenge, err = issue(testUserID, testIPHash, "prism")
		require.NoError(t, err)
		require.NoError(t, verify(challenge.Value, solve(t, challenge.Value, difficulty), testUserID, testIPHash))
	})

	t.Run("difficulty is clamped to the sanity ceiling", func(t *testing.T) {
		t.Parallel()
		c := &clock{now: testTime}
		issue, _ := scheme(t, [][]byte{testKey(t, 1)}, proofofwork.MaxDifficulty+10, c)

		challenge, err := issue(testUserID, testIPHash, "prism")
		require.NoError(t, err)
		require.Equal(t, proofofwork.MaxDifficulty, challenge.Difficulty,
			"a bug in a future difficulty signal must not be able to ask for work no client will finish")
	})

	t.Run("rejects a tampered difficulty", func(t *testing.T) {
		t.Parallel()
		c := &clock{now: testTime}
		issue, verify := scheme(t, [][]byte{testKey(t, 1)}, 12, c)

		challenge, err := issue(testUserID, testIPHash, "prism")
		require.NoError(t, err)

		// The obvious attack on a self-describing challenge: keep the
		// signature, rewrite the work it asks for.
		body, signature, ok := strings.Cut(challenge.Value, ".")
		require.True(t, ok)
		rawPayload, err := base64.RawURLEncoding.DecodeString(body)
		require.NoError(t, err)
		var payload map[string]any
		require.NoError(t, json.Unmarshal(rawPayload, &payload))
		payload["difficulty"] = 0
		rewritten, err := json.Marshal(payload)
		require.NoError(t, err)
		tampered := base64.RawURLEncoding.EncodeToString(rewritten) + "." + signature

		require.ErrorIs(t, verify(tampered, "0", testUserID, testIPHash), proofofwork.ErrBadSignature)
	})

	t.Run("rejects a challenge signed with an unknown key", func(t *testing.T) {
		t.Parallel()
		c := &clock{now: testTime}
		issue, _ := scheme(t, [][]byte{testKey(t, 1)}, 0, c)
		_, verifyOther := scheme(t, [][]byte{testKey(t, 2)}, 0, c)

		challenge, err := issue(testUserID, testIPHash, "prism")
		require.NoError(t, err)
		require.ErrorIs(t, verifyOther(challenge.Value, "0", testUserID, testIPHash), proofofwork.ErrBadSignature)
	})

	t.Run("rotation: mints with the first key, accepts every key", func(t *testing.T) {
		t.Parallel()
		c := &clock{now: testTime}
		oldKey, newKey := testKey(t, 1), testKey(t, 2)

		// Before the rotation deploy: minted with the old key.
		issueOld, _ := scheme(t, [][]byte{oldKey}, 0, c)
		challenge, err := issueOld(testUserID, testIPHash, "prism")
		require.NoError(t, err)

		// After it: the new key signs, but the outstanding challenge from
		// the previous revision still verifies.
		issueNew, verifyBoth := scheme(t, [][]byte{newKey, oldKey}, 0, c)
		require.NoError(t, verifyBoth(challenge.Value, solve(t, challenge.Value, 0), testUserID, testIPHash))

		fresh, err := issueNew(testUserID, testIPHash, "prism")
		require.NoError(t, err)
		_, verifyNewOnly := scheme(t, [][]byte{newKey}, 0, c)
		require.NoError(t, verifyNewOnly(fresh.Value, solve(t, fresh.Value, 0), testUserID, testIPHash),
			"new challenges must be signed with the first key, or dropping the old one breaks them")
	})

	t.Run("rejects an expired challenge", func(t *testing.T) {
		t.Parallel()
		c := &clock{now: testTime}
		issue, verify := scheme(t, [][]byte{testKey(t, 1)}, 0, c)

		challenge, err := issue(testUserID, testIPHash, "prism")
		require.NoError(t, err)

		c.now = testTime.Add(59 * time.Second)
		require.NoError(t, verify(challenge.Value, solve(t, challenge.Value, 0), testUserID, testIPHash),
			"still inside the 60s window")

		challenge, err = issue(testUserID, testIPHash, "prism")
		require.NoError(t, err)
		c.now = c.now.Add(61 * time.Second)
		require.ErrorIs(t, verify(challenge.Value, solve(t, challenge.Value, 0), testUserID, testIPHash), proofofwork.ErrChallengeExpired)
	})

	t.Run("rejects a challenge issued in the future", func(t *testing.T) {
		t.Parallel()
		c := &clock{now: testTime}
		issue, verify := scheme(t, [][]byte{testKey(t, 1)}, 0, c)

		challenge, err := issue(testUserID, testIPHash, "prism")
		require.NoError(t, err)

		// Our own clock jumping backwards, not anything the caller did.
		// The client recovers by asking for another challenge.
		c.now = testTime.Add(-5 * time.Minute)
		require.ErrorIs(t, verify(challenge.Value, solve(t, challenge.Value, 0), testUserID, testIPHash), proofofwork.ErrChallengeExpired)
	})

	t.Run("tolerates a verifier whose clock trails the minter's", func(t *testing.T) {
		t.Parallel()
		c := &clock{now: testTime}
		issue, verify := scheme(t, [][]byte{testKey(t, 1)}, 0, c)

		challenge, err := issue(testUserID, testIPHash, "prism")
		require.NoError(t, err)
		solution := solve(t, challenge.Value, 0)

		// A rollout serves two revisions whose clocks can disagree.
		c.now = testTime.Add(-2 * time.Second)
		require.NoError(t, verify(challenge.Value, solution, testUserID, testIPHash),
			"a small backwards skew must not reject a challenge we just minted")

		challenge, err = issue(testUserID, testIPHash, "prism")
		require.NoError(t, err)
		c.now = testTime.Add(-30 * time.Second)
		require.ErrorIs(t, verify(challenge.Value, solve(t, challenge.Value, 0), testUserID, testIPHash),
			proofofwork.ErrChallengeExpired,
			"the grace is a tolerance, not an open window into the future")
	})

	t.Run("the algorithm travels signed", func(t *testing.T) {
		t.Parallel()
		c := &clock{now: testTime}
		issue, verify := scheme(t, [][]byte{testKey(t, 1)}, 0, c)

		challenge, err := issue(testUserID, testIPHash, "prism")
		require.NoError(t, err)
		require.Equal(t, proofofwork.AlgorithmSHA256LeadingZeros, challenge.Algorithm)

		body, _, ok := strings.Cut(challenge.Value, ".")
		require.True(t, ok)
		rawPayload, err := base64.RawURLEncoding.DecodeString(body)
		require.NoError(t, err)
		var payload struct {
			Algorithm string `json:"alg"`
		}
		require.NoError(t, json.Unmarshal(rawPayload, &payload))
		require.Equal(t, proofofwork.AlgorithmSHA256LeadingZeros, payload.Algorithm,
			"the scheme has to be inside the signed blob, or verification is guessing")

		require.NoError(t, verify(challenge.Value, solve(t, challenge.Value, 0), testUserID, testIPHash))
	})

	// Adding a v2 later means an outgoing revision gets handed v2 challenges
	// mid-rollout. Without the field it would verify them as v1 and reject
	// correct solutions as insufficient work.
	t.Run("refuses a scheme it does not implement, without spending it", func(t *testing.T) {
		t.Parallel()
		key := testKey(t, 1)
		c := &clock{now: testTime}
		_, verify := scheme(t, [][]byte{key}, 0, c)

		future := signPayload(t, key, fmt.Sprintf(
			`{"nonce":"future-scheme-nonce","userId":%q,"ipHash":%q,"issuedAtUnixMillis":%d,"difficulty":0,"alg":"argon2id-v2"}`,
			testUserID, testIPHash, testTime.UnixMilli(),
		))

		err := verify(future, "0", testUserID, testIPHash)
		require.ErrorIs(t, err, proofofwork.ErrUnsupportedAlgorithm)
		require.NotErrorIs(t, err, proofofwork.ErrInsufficientWork,
			"a scheme we can't check is not the client doing too little work")

		missing := signPayload(t, key, fmt.Sprintf(
			`{"nonce":"no-alg-nonce","userId":%q,"ipHash":%q,"issuedAtUnixMillis":%d,"difficulty":0}`,
			testUserID, testIPHash, testTime.UnixMilli(),
		))
		require.ErrorIs(t, verify(missing, solve(t, missing, 0), testUserID, testIPHash),
			proofofwork.ErrUnsupportedAlgorithm,
			"an absent scheme is refused rather than defaulted: nothing has ever minted one")
	})

	t.Run("rejects a tampered algorithm", func(t *testing.T) {
		t.Parallel()
		c := &clock{now: testTime}
		issue, verify := scheme(t, [][]byte{testKey(t, 1)}, 12, c)

		challenge, err := issue(testUserID, testIPHash, "prism")
		require.NoError(t, err)

		// Downgrading the scheme is the same attack as downgrading the
		// difficulty.
		body, signature, ok := strings.Cut(challenge.Value, ".")
		require.True(t, ok)
		rawPayload, err := base64.RawURLEncoding.DecodeString(body)
		require.NoError(t, err)
		var payload map[string]any
		require.NoError(t, json.Unmarshal(rawPayload, &payload))
		payload["alg"] = "something-easier"
		rewritten, err := json.Marshal(payload)
		require.NoError(t, err)
		tampered := base64.RawURLEncoding.EncodeToString(rewritten) + "." + signature

		require.ErrorIs(t, verify(tampered, "0", testUserID, testIPHash), proofofwork.ErrBadSignature)
	})

	t.Run("rejects a challenge presented from another ip", func(t *testing.T) {
		t.Parallel()
		c := &clock{now: testTime}
		issue, verify := scheme(t, [][]byte{testKey(t, 1)}, 0, c)

		challenge, err := issue(testUserID, testIPHash, "prism")
		require.NoError(t, err)
		solution := solve(t, challenge.Value, 0)

		otherIPHash := strings.Repeat("a", 64)
		require.ErrorIs(t, verify(challenge.Value, solution, testUserID, otherIPHash), proofofwork.ErrIPMismatch,
			"one rented CPU box must not solve challenges for a pool of proxy exits")
		require.NoError(t, verify(challenge.Value, solution, testUserID, testIPHash))
	})

	t.Run("rejects a challenge presented for another user id", func(t *testing.T) {
		t.Parallel()
		c := &clock{now: testTime}
		issue, verify := scheme(t, [][]byte{testKey(t, 1)}, 0, c)

		challenge, err := issue(testUserID, testIPHash, "prism")
		require.NoError(t, err)
		solution := solve(t, challenge.Value, 0)

		require.ErrorIs(t, verify(challenge.Value, solution, "someone-else", testIPHash), proofofwork.ErrUserIDMismatch,
			"a second identity has to cost a second solve, or the work prices nothing")
		require.NoError(t, verify(challenge.Value, solution, testUserID, testIPHash))
	})

	t.Run("the user id is compared byte for byte", func(t *testing.T) {
		t.Parallel()
		c := &clock{now: testTime}
		issue, verify := scheme(t, [][]byte{testKey(t, 1)}, 0, c)

		challenge, err := issue(testUserID, testIPHash, "prism")
		require.NoError(t, err)
		solution := solve(t, challenge.Value, 0)

		// No trimming, no case folding: whatever normalization either side
		// grew unilaterally would reject correct solutions.
		for _, near := range []string{" " + testUserID, testUserID + " ", strings.ToUpper(testUserID), testUserID + "\x00"} {
			require.ErrorIs(t, verify(challenge.Value, solution, near, testIPHash), proofofwork.ErrUserIDMismatch)
		}
	})

	// Replay is what the used-nonce set used to prevent. It is allowed now:
	// the binding above means a reused solution only ever mints sessions for
	// one identity, which shares one budget — the multiple-tabs case.
	t.Run("a solved challenge can be presented again inside its ttl", func(t *testing.T) {
		t.Parallel()
		c := &clock{now: testTime}
		issue, verify := scheme(t, [][]byte{testKey(t, 1)}, 0, c)

		challenge, err := issue(testUserID, testIPHash, "prism")
		require.NoError(t, err)
		solution := solve(t, challenge.Value, 0)

		require.NoError(t, verify(challenge.Value, solution, testUserID, testIPHash))
		require.NoError(t, verify(challenge.Value, solution, testUserID, testIPHash))

		// The ttl is the whole bound on that window.
		c.now = testTime.Add(61 * time.Second)
		require.ErrorIs(t, verify(challenge.Value, solution, testUserID, testIPHash), proofofwork.ErrChallengeExpired)
	})

	t.Run("a wrong solution does not cost the challenge", func(t *testing.T) {
		t.Parallel()
		const difficulty = 10
		c := &clock{now: testTime}
		issue, verify := scheme(t, [][]byte{testKey(t, 1)}, difficulty, c)

		challenge, err := issue(testUserID, testIPHash, "prism")
		require.NoError(t, err)
		// Not a fixed string: against a random challenge one would clear a
		// 10-bit bar about one run in a thousand.
		wrong := solveShortOf(t, challenge.Value, 0, difficulty)
		require.ErrorIs(t, verify(challenge.Value, wrong, testUserID, testIPHash), proofofwork.ErrInsufficientWork)
		require.NoError(t, verify(challenge.Value, solve(t, challenge.Value, difficulty), testUserID, testIPHash),
			"nothing is spent before the work is checked, so a client bug doesn't cost a round trip")
	})

	t.Run("rejects malformed challenges", func(t *testing.T) {
		t.Parallel()
		c := &clock{now: testTime}
		_, verify := scheme(t, [][]byte{testKey(t, 1)}, 0, c)

		for name, value := range map[string]string{
			"empty":             "",
			"no separator":      "abcdef",
			"signature not b64": "abcdef.not base64!",
			"empty signature":   "abcdef.",
		} {
			t.Run(name, func(t *testing.T) {
				t.Parallel()
				err := verify(value, "0", testUserID, testIPHash)
				require.Error(t, err)
				require.NotErrorIs(t, err, proofofwork.ErrInsufficientWork)
			})
		}
	})
}

func TestBuildersRejectInvalidConfig(t *testing.T) {
	t.Parallel()

	keys := [][]byte{testKey(t, 1)}

	_, err := proofofwork.BuildIssueChallenge(nil, fixedDifficulty(0), time.Now)
	require.ErrorIs(t, err, proofofwork.ErrInvalidConfig)

	_, err = proofofwork.BuildIssueChallenge(keys, nil, time.Now)
	require.ErrorIs(t, err, proofofwork.ErrInvalidConfig)

	_, err = proofofwork.BuildParseChallenge(nil, time.Now)
	require.ErrorIs(t, err, proofofwork.ErrInvalidConfig)
}

func TestParseAndCheck(t *testing.T) {
	t.Parallel()

	// The split is what lets the caller observe a challenge without asking
	// which of its fields are trustworthy: parse refuses everything that
	// carries nothing interpretable, check refuses everything else.
	t.Run("parse refuses what cannot be observed", func(t *testing.T) {
		t.Parallel()
		key := testKey(t, 1)
		c := &clock{now: testTime}
		issue, parse := parsingScheme(t, [][]byte{key}, 0, c)

		challenge, err := issue(testUserID, testIPHash, "prism")
		require.NoError(t, err)
		body, signature, ok := strings.Cut(challenge.Value, ".")
		require.True(t, ok)

		otherKey := signPayload(t, testKey(t, 2), fmt.Sprintf(
			`{"nonce":"n","userId":%q,"ipHash":%q,"issuedAtUnixMillis":%d,"difficulty":0,"alg":%q}`,
			testUserID, testIPHash, testTime.UnixMilli(), proofofwork.AlgorithmSHA256LeadingZeros,
		))
		futureScheme := signPayload(t, key, fmt.Sprintf(
			`{"nonce":"n","userId":%q,"ipHash":%q,"issuedAtUnixMillis":%d,"difficulty":0,"alg":"argon2id-v2"}`,
			testUserID, testIPHash, testTime.UnixMilli(),
		))

		for name, tc := range map[string]struct {
			challenge string
			want      error
		}{
			"no separator":          {"abcdef", proofofwork.ErrMalformedChallenge},
			"signature not b64":     {"abcdef.not base64!", proofofwork.ErrMalformedChallenge},
			"payload not b64":       {"not base64!." + signature, proofofwork.ErrBadSignature},
			"unknown key":           {otherKey, proofofwork.ErrBadSignature},
			"unsupported algorithm": {futureScheme, proofofwork.ErrUnsupportedAlgorithm},
		} {
			t.Run(name, func(t *testing.T) {
				t.Parallel()
				signed, err := parse(tc.challenge)
				require.ErrorIs(t, err, tc.want)
				require.Nil(t, signed)
			})
		}

		signed, err := parse(body + "." + signature)
		require.NoError(t, err)
		require.NotNil(t, signed)
	})

	// An expired challenge parses so the caller can still observe it: how far
	// past the ttl it came back is the whole signal for a difficulty set past
	// what clients can finish.
	t.Run("check owns freshness, so an expired challenge still parses", func(t *testing.T) {
		t.Parallel()
		c := &clock{now: testTime}
		issue, parse := parsingScheme(t, [][]byte{testKey(t, 1)}, 0, c)

		challenge, err := issue(testUserID, testIPHash, "prism")
		require.NoError(t, err)
		solution := solve(t, challenge.Value, 0)

		c.now = testTime.Add(90 * time.Second)
		signed, err := parse(challenge.Value)
		require.NoError(t, err)
		require.Equal(t, 90*time.Second, signed.Age())
		require.ErrorIs(t, signed.Check(solution, testUserID, testIPHash), proofofwork.ErrChallengeExpired)
	})

	t.Run("age is measured from the mint instant", func(t *testing.T) {
		t.Parallel()
		c := &clock{now: testTime}
		issue, parse := parsingScheme(t, [][]byte{testKey(t, 1)}, 0, c)

		challenge, err := issue(testUserID, testIPHash, "prism")
		require.NoError(t, err)

		signed, err := parse(challenge.Value)
		require.NoError(t, err)
		require.Zero(t, signed.Age())

		c.now = testTime.Add(1500 * time.Millisecond)
		require.Equal(t, 1500*time.Millisecond, signed.Age(),
			"milliseconds, because a difficulty-0 handshake is a round trip")

		// Our own clock stepping backwards is not a measurement. The caller
		// recording it has to drop this rather than poison the histogram.
		c.now = testTime.Add(-2 * time.Second)
		require.Negative(t, signed.Age())
	})

	t.Run("difficulty comes from the signed payload, not the dial", func(t *testing.T) {
		t.Parallel()
		const minted = 6
		keys := [][]byte{testKey(t, 1)}
		c := &clock{now: testTime}
		issue, _ := parsingScheme(t, keys, minted, c)

		challenge, err := issue(testUserID, testIPHash, "prism")
		require.NoError(t, err)

		// The dial moved after minting — the point of it being server-side.
		_, parse := parsingScheme(t, keys, 20, c)
		signed, err := parse(challenge.Value)
		require.NoError(t, err)
		require.Equal(t, minted, signed.Difficulty(),
			"reporting the current dial would label the sample with work the client was never asked for")
		require.NoError(t, signed.Check(solve(t, challenge.Value, minted), testUserID, testIPHash))
	})
}

func TestRejectionReason(t *testing.T) {
	t.Parallel()

	// The label set is bounded and each cause is distinguishable — a
	// difficulty change and a client bug must not look the same.
	seen := map[string]struct{}{}
	for _, err := range []error{
		proofofwork.ErrMalformedChallenge,
		proofofwork.ErrBadSignature,
		proofofwork.ErrChallengeExpired,
		proofofwork.ErrIPMismatch,
		proofofwork.ErrUserIDMismatch,
		proofofwork.ErrInsufficientWork,
		proofofwork.ErrUnsupportedAlgorithm,
	} {
		reason := proofofwork.RejectionReason(err)
		require.NotEqual(t, "other", reason, "every sentinel needs its own label")
		require.NotContains(t, seen, reason)
		seen[reason] = struct{}{}
	}
	require.Equal(t, "other", proofofwork.RejectionReason(errUnexpected))
}
