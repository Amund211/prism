import { afterEach, describe, expect, test, vi } from "vitest";

import { makeSessionResponse } from "#mocks/data.ts";

import { anonymousLogin, refreshSession } from "./api.ts";
import type { Session } from "./storage.ts";

// The shape the stateless cutover mints. Unlike the stored value, an
// unacceptable handle here *throws* rather than costing one re-login, so this
// path is the one the cutover cannot get wrong.
const STATELESS_SESSION_ID = "flsess_eyJ0eXAiOiJmbHNlc3MvMSJ9.c2lnbmF0dXJl";

// oxlint-disable-next-line typescript/prefer-readonly-parameter-types
const mockFetch = (response: Response) => {
    // typeof fetch, not a bare thunk: it types mock.calls, so a call-shape
    // assertion needs no cast and stops compiling if the call shape changes.
    const fetchMock = vi.fn<typeof fetch>();
    // One response, read once: every test here drives a single request. A test
    // that drives two (refresh then login, as session.ts does) needs a fresh
    // Response per call, or the second read fails with "body already read".
    fetchMock.mockResolvedValue(response);
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
};

const login = async (): Promise<Session> =>
    anonymousLogin({ userId: "rnb_test", challenge: "abc", solution: "1" });

afterEach(() => {
    vi.unstubAllGlobals();
});

describe(anonymousLogin, () => {
    test("accepts a dotted, stateless handle", async () => {
        mockFetch(Response.json(makeSessionResponse(STATELESS_SESSION_ID)));

        await expect(login()).resolves.toStrictEqual({
            sessionId: STATELESS_SESSION_ID,
            tier: "anonymous",
        });
    });

    test("keeps the tier the server returned", async () => {
        mockFetch(
            Response.json(makeSessionResponse(STATELESS_SESSION_ID, "microsoft")),
        );

        await expect(login()).resolves.toStrictEqual({
            sessionId: STATELESS_SESSION_ID,
            tier: "microsoft",
        });
    });

    // A tier this client does not know is a usable session under an unusable
    // label, so it is relabelled rather than dropped. Storing it verbatim would
    // be worse: readSession rejects an unknown tier and clears the key, which
    // costs a fresh login on every page load.
    test("falls back to anonymous on an unknown tier", async () => {
        mockFetch(Response.json(makeSessionResponse(STATELESS_SESSION_ID, "premium")));

        await expect(login()).resolves.toStrictEqual({
            sessionId: STATELESS_SESSION_ID,
            tier: "anonymous",
        });
    });

    test("rejects a handle without the prefix", async () => {
        mockFetch(Response.json(makeSessionResponse("sess_no_prefix")));

        await expect(login()).rejects.toThrow("Invalid session id");
    });
});

describe(refreshSession, () => {
    const stale: Session = { sessionId: "flsess_stale", tier: "microsoft" };

    test("sends the stale handle as the bearer, and accepts a dotted one back", async () => {
        const fetchMock = mockFetch(
            Response.json(makeSessionResponse(STATELESS_SESSION_ID, "microsoft")),
        );

        await expect(refreshSession(stale)).resolves.toStrictEqual({
            sessionId: STATELESS_SESSION_ID,
            tier: "microsoft",
        });

        const [url, init] = fetchMock.mock.calls[0] ?? [];
        expect(url).toStrictEqual(expect.stringContaining("/v1/auth/refresh"));
        expect(new Headers(init?.headers).get("Authorization")).toBe(
            `Bearer ${stale.sessionId}`,
        );
    });

    test("returns null on a 401 so the caller logs in again", async () => {
        mockFetch(new Response("unauthorized", { status: 401 }));

        await expect(refreshSession(stale)).resolves.toBeNull();
    });

    // The same object, not an equal one: the stored session is untouched and
    // must be reused.
    test("returns the session unchanged on a 429", async () => {
        mockFetch(new Response("too many requests", { status: 429 }));

        await expect(refreshSession(stale)).resolves.toBe(stale);
    });

    // Only a 401 means "finished" — session.ts clears the stored session on a
    // null, so folding a transient failure into one costs a full re-login.
    test("rethrows any other error status", async () => {
        mockFetch(new Response("boom", { status: 500 }));

        await expect(refreshSession(stale)).rejects.toThrow("500");
    });
});
