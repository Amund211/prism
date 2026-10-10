import { delay, http, HttpResponse } from "msw";
import { afterEach, describe, expect, vi } from "vitest";
import { renderHook } from "vitest-browser-react";

import { flashlightFetch } from "#helpers/flashlight/fetch.ts";
import {
    makeMicrosoftSessionResponse,
    makeSessionResponse,
    TEST_SESSION_ID,
    USERS,
} from "#mocks/data.ts";
import { mswTest } from "#test/msw-test.ts";

import { adoptSession, ensureSession, signOutEverywhere } from "./session.ts";
import { clearSession, readSession, writeSession } from "./storage.ts";
import { useAuthSession } from "./useAuthSession.ts";

const endpoint = (path: string) => `http://localhost:5173/flashlight/${path}`;

const fetchThing = async () =>
    flashlightFetch<{ ok: boolean }>("/v1/thing", {
        errorContext: "Failed to get thing",
        extra: {},
    });

describe("anonymous auth", () => {
    mswTest(
        "logs in and sends the bearer when nothing is stored",
        async ({ worker }) => {
            const bearers: (string | null)[] = [];
            worker.use(
                http.get(endpoint("v1/thing"), ({ request }) => {
                    bearers.push(request.headers.get("Authorization"));
                    return HttpResponse.json({ ok: true });
                }),
            );

            await expect(fetchThing()).resolves.toStrictEqual({ ok: true });

            expect(bearers).toStrictEqual([`Bearer ${TEST_SESSION_ID}`]);
            expect(readSession()).toStrictEqual({
                sessionId: TEST_SESSION_ID,
                tier: "anonymous",
            });
        },
    );

    mswTest("refreshes and retries on a 401", async ({ worker }) => {
        writeSession({ sessionId: "flsess_stale", tier: "anonymous" });

        const bearers: (string | null)[] = [];
        let refreshes = 0;
        worker.use(
            http.post(endpoint("v1/auth/refresh"), () => {
                refreshes++;
                return HttpResponse.json(makeSessionResponse("flsess_fresh"));
            }),
            http.get(endpoint("v1/thing"), ({ request }) => {
                const bearer = request.headers.get("Authorization");
                bearers.push(bearer);
                if (bearer === "Bearer flsess_stale") {
                    return new HttpResponse(null, { status: 401 });
                }
                return HttpResponse.json({ ok: true });
            }),
        );

        await expect(fetchThing()).resolves.toStrictEqual({ ok: true });

        expect(refreshes).toBe(1);
        expect(bearers).toStrictEqual(["Bearer flsess_stale", "Bearer flsess_fresh"]);
        expect(readSession()?.sessionId).toBe("flsess_fresh");
    });

    mswTest("logs in again when the refresh 401s", async ({ worker }) => {
        writeSession({ sessionId: "flsess_dead", tier: "anonymous" });

        const bearers: (string | null)[] = [];
        let logins = 0;
        worker.use(
            http.post(
                endpoint("v1/auth/refresh"),
                () => new HttpResponse(null, { status: 401 }),
            ),
            http.post(endpoint("v1/auth/anonymous/login"), () => {
                logins++;
                return HttpResponse.json(makeSessionResponse());
            }),
            http.get(endpoint("v1/thing"), ({ request }) => {
                const bearer = request.headers.get("Authorization");
                bearers.push(bearer);
                if (bearer === "Bearer flsess_dead") {
                    return new HttpResponse(null, { status: 401 });
                }
                return HttpResponse.json({ ok: true });
            }),
        );

        await expect(fetchThing()).resolves.toStrictEqual({ ok: true });

        expect(logins).toBe(1);
        expect(bearers).toStrictEqual([
            "Bearer flsess_dead",
            `Bearer ${TEST_SESSION_ID}`,
        ]);
    });

    mswTest("clears the stored session when the refresh 401s", async ({ worker }) => {
        writeSession({ sessionId: "flsess_dead", tier: "anonymous" });

        worker.use(
            http.post(
                endpoint("v1/auth/refresh"),
                () => new HttpResponse(null, { status: 401 }),
            ),
            http.post(
                endpoint("v1/auth/anonymous/login"),
                () => new HttpResponse(null, { status: 503 }),
            ),
            http.get(
                endpoint("v1/thing"),
                () => new HttpResponse(null, { status: 401 }),
            ),
        );

        await expect(fetchThing()).rejects.toThrow("Failed to log in anonymously");

        expect(readSession()).toBeNull();
    });

    mswTest("keeps the stored session when the refresh 429s", async ({ worker }) => {
        writeSession({ sessionId: "flsess_throttled", tier: "anonymous" });

        const bearers: (string | null)[] = [];
        let logins = 0;
        worker.use(
            http.post(
                endpoint("v1/auth/refresh"),
                () => new HttpResponse(null, { status: 429 }),
            ),
            http.post(endpoint("v1/auth/anonymous/login"), () => {
                logins++;
                return HttpResponse.json(makeSessionResponse());
            }),
            http.get(endpoint("v1/thing"), ({ request }) => {
                bearers.push(request.headers.get("Authorization"));
                // Only the first attempt 401s: the throttled refresh means the
                // session is still good.
                if (bearers.length === 1) {
                    return new HttpResponse(null, { status: 401 });
                }
                return HttpResponse.json({ ok: true });
            }),
        );

        await expect(fetchThing()).resolves.toStrictEqual({ ok: true });

        expect(logins).toBe(0);
        expect(bearers).toStrictEqual([
            "Bearer flsess_throttled",
            "Bearer flsess_throttled",
        ]);
        expect(readSession()?.sessionId).toBe("flsess_throttled");
    });

    mswTest("logs in once for a concurrent fan-out", async ({ worker }) => {
        let logins = 0;
        let challenges = 0;
        worker.use(
            http.post(endpoint("v1/auth/anonymous/challenge"), () => {
                challenges++;
                return HttpResponse.json({
                    challenge: "challenge",
                    algorithm: "sha256-leading-zeros-v1",
                    difficulty: 0,
                    expiresInSeconds: 60,
                });
            }),
            http.post(endpoint("v1/auth/anonymous/login"), () => {
                logins++;
                return HttpResponse.json(makeSessionResponse());
            }),
            http.get(endpoint("v1/thing"), () => HttpResponse.json({ ok: true })),
        );

        await Promise.all([fetchThing(), fetchThing(), fetchThing()]);

        expect(challenges).toBe(1);
        expect(logins).toBe(1);
    });

    mswTest(
        "never calls recover when an anonymous refresh 401s",
        async ({ worker }) => {
            writeSession({ sessionId: "flsess_dead", tier: "anonymous" });

            let recovers = 0;
            worker.use(
                http.post(
                    endpoint("v1/auth/refresh"),
                    () => new HttpResponse(null, { status: 401 }),
                ),
                http.post(endpoint("v1/auth/recover"), () => {
                    recovers++;
                    return HttpResponse.json(makeMicrosoftSessionResponse());
                }),
                http.get(endpoint("v1/thing"), ({ request }) =>
                    request.headers.get("Authorization") === "Bearer flsess_dead"
                        ? new HttpResponse(null, { status: 401 })
                        : HttpResponse.json({ ok: true }),
                ),
            );

            await expect(fetchThing()).resolves.toStrictEqual({ ok: true });

            expect(recovers).toBe(0);
            expect(readSession()?.tier).toBe("anonymous");
        },
    );

    mswTest("discards a corrupted stored session", async ({ worker }) => {
        localStorage.setItem("rainbow_auth_session", '{"v":1,"sessionId":"nope"}');

        const bearers: (string | null)[] = [];
        worker.use(
            http.get(endpoint("v1/thing"), ({ request }) => {
                bearers.push(request.headers.get("Authorization"));
                return HttpResponse.json({ ok: true });
            }),
        );

        await expect(fetchThing()).resolves.toStrictEqual({ ok: true });

        expect(bearers).toStrictEqual([`Bearer ${TEST_SESSION_ID}`]);
    });
});

describe("microsoft auth", () => {
    const { uuid } = USERS.player1;

    afterEach(() => {
        vi.restoreAllMocks();
    });

    const failOn = (bearer: string) =>
        http.get(endpoint("v1/thing"), ({ request }) =>
            request.headers.get("Authorization") === `Bearer ${bearer}`
                ? new HttpResponse(null, { status: 401 })
                : HttpResponse.json({ ok: true }),
        );

    const refresh401 = http.post(
        endpoint("v1/auth/refresh"),
        () => new HttpResponse(null, { status: 401 }),
    );

    // Refresh does not return the uuid, so the client carries it forward.
    mswTest("keeps the uuid across a refresh", async ({ worker }) => {
        writeSession({ sessionId: "flsess_ms_stale", tier: "microsoft", uuid });

        worker.use(
            http.post(endpoint("v1/auth/refresh"), () =>
                HttpResponse.json(makeSessionResponse("flsess_ms_fresh", "microsoft")),
            ),
            failOn("flsess_ms_stale"),
        );

        await expect(fetchThing()).resolves.toStrictEqual({ ok: true });

        expect(readSession()).toStrictEqual({
            sessionId: "flsess_ms_fresh",
            tier: "microsoft",
            uuid,
        });
    });

    mswTest("recovers and retries when the refresh 401s", async ({ worker }) => {
        writeSession({ sessionId: "flsess_ms_dead", tier: "microsoft", uuid });

        const bearers: (string | null)[] = [];
        let recovers = 0;
        let logins = 0;
        worker.use(
            refresh401,
            http.post(endpoint("v1/auth/recover"), ({ request }) => {
                recovers++;
                // Only recover sends the cookie, and never a bearer.
                expect(request.headers.get("Authorization")).toBeNull();
                expect(request.credentials).toBe("include");
                return HttpResponse.json(
                    makeMicrosoftSessionResponse("flsess_ms_recovered", uuid),
                );
            }),
            http.post(endpoint("v1/auth/anonymous/login"), () => {
                logins++;
                return HttpResponse.json(makeSessionResponse());
            }),
            http.get(endpoint("v1/thing"), ({ request }) => {
                const bearer = request.headers.get("Authorization");
                bearers.push(bearer);
                // Data requests never carry the cookie.
                expect(request.credentials).not.toBe("include");
                return bearer === "Bearer flsess_ms_dead"
                    ? new HttpResponse(null, { status: 401 })
                    : HttpResponse.json({ ok: true });
            }),
        );

        await expect(fetchThing()).resolves.toStrictEqual({ ok: true });

        expect(recovers).toBe(1);
        expect(logins).toBe(0);
        expect(bearers).toStrictEqual([
            "Bearer flsess_ms_dead",
            "Bearer flsess_ms_recovered",
        ]);
        expect(readSession()).toStrictEqual({
            sessionId: "flsess_ms_recovered",
            tier: "microsoft",
            uuid,
        });
    });

    mswTest("falls back to anonymous when recover 401s", async ({ worker }) => {
        writeSession({ sessionId: "flsess_ms_dead", tier: "microsoft", uuid });

        worker.use(
            refresh401,
            http.post(
                endpoint("v1/auth/recover"),
                () => new HttpResponse("unauthorized", { status: 401 }),
            ),
            failOn("flsess_ms_dead"),
        );

        await expect(fetchThing()).resolves.toStrictEqual({ ok: true });

        expect(readSession()).toStrictEqual({
            sessionId: TEST_SESSION_ID,
            tier: "anonymous",
        });
    });

    mswTest.for([429, 500, 503])(
        "keeps the microsoft session when recover returns %i",
        async (status, { worker }) => {
            const session = {
                sessionId: "flsess_ms_dead",
                tier: "microsoft",
                uuid,
            } as const;
            writeSession(session);

            let logins = 0;
            worker.use(
                refresh401,
                http.post(
                    endpoint("v1/auth/recover"),
                    () => new HttpResponse("nope", { status }),
                ),
                http.post(endpoint("v1/auth/anonymous/login"), () => {
                    logins++;
                    return HttpResponse.json(makeSessionResponse());
                }),
                failOn("flsess_ms_dead"),
            );

            await expect(fetchThing()).rejects.toThrow("Failed to recover");

            expect(logins).toBe(0);
            expect(readSession()).toStrictEqual(session);
        },
    );

    // Without Web Locks (or past the lock timeout) only the in-flight promise
    // orders the two writes.
    mswTest(
        "adoptSession is not overwritten by an in-flight anonymous login",
        async ({ worker }) => {
            vi.spyOn(navigator, "locks", "get").mockReturnValue(
                undefined as unknown as LockManager,
            );
            worker.use(
                http.post(endpoint("v1/auth/anonymous/login"), async () => {
                    await delay(100);
                    return HttpResponse.json(makeSessionResponse());
                }),
            );
            const session = {
                sessionId: "flsess_ms_new",
                tier: "microsoft",
                uuid,
            } as const;

            const anonymous = ensureSession(null);
            const adopted = adoptSession(session);
            await Promise.all([anonymous, adopted]);

            expect(readSession()).toStrictEqual(session);
        },
    );

    mswTest(
        "an ensureSession that starts during adoptSession gets the adopted session",
        async ({ worker }) => {
            vi.spyOn(navigator, "locks", "get").mockReturnValue(
                undefined as unknown as LockManager,
            );
            let logins = 0;
            worker.use(
                http.post(endpoint("v1/auth/anonymous/login"), () => {
                    logins++;
                    return HttpResponse.json(makeSessionResponse());
                }),
            );
            const session = {
                sessionId: "flsess_ms_new",
                tier: "microsoft",
                uuid,
            } as const;

            const adopted = adoptSession(session);
            const later = ensureSession(null);

            await expect(later).resolves.toStrictEqual(session);
            await adopted;
            expect(logins).toBe(0);
            expect(readSession()).toStrictEqual(session);
        },
    );

    mswTest(
        "an ensureSession after the previous acquire settles waits for adoptSession",
        async ({ worker }) => {
            // No exclusion: the second request (the adopt's) is granted late,
            // like a lock held by another tab.
            const grantDelays = [0, 100];
            const locks = {
                request: async (
                    _name: string,
                    _options: unknown,
                    run: () => Promise<unknown>,
                ) => {
                    await delay(grantDelays.shift() ?? 0);
                    return run();
                },
            };
            vi.spyOn(navigator, "locks", "get").mockReturnValue(
                locks as unknown as LockManager,
            );
            let logins = 0;
            worker.use(
                http.post(endpoint("v1/auth/anonymous/login"), async () => {
                    logins++;
                    await delay(50);
                    return HttpResponse.json(makeSessionResponse());
                }),
            );
            const session = {
                sessionId: "flsess_ms_new",
                tier: "microsoft",
                uuid,
            } as const;

            const anonymous = ensureSession(null);
            const adopted = adoptSession(session);
            await anonymous;
            const later = ensureSession(null);

            await expect(later).resolves.toStrictEqual(session);
            await adopted;
            expect(logins).toBe(1);
            expect(readSession()).toStrictEqual(session);
        },
    );

    mswTest(
        "signOutEverywhere logs out and ends with an anonymous session",
        async ({ worker }) => {
            writeSession({ sessionId: "flsess_ms", tier: "microsoft", uuid });
            let logouts = 0;
            worker.use(
                http.post(endpoint("v1/auth/logout"), ({ request }) => {
                    logouts++;
                    expect(request.credentials).toBe("include");
                    return new HttpResponse(null, { status: 204 });
                }),
            );

            await signOutEverywhere();

            expect(logouts).toBe(1);
            expect(readSession()).toStrictEqual({
                sessionId: TEST_SESSION_ID,
                tier: "anonymous",
            });
        },
    );

    mswTest(
        "signOutEverywhere keeps the session when logout fails",
        async ({ worker }) => {
            const session = {
                sessionId: "flsess_ms",
                tier: "microsoft",
                uuid,
            } as const;
            writeSession(session);
            worker.use(
                http.post(
                    endpoint("v1/auth/logout"),
                    () => new HttpResponse("nope", { status: 500 }),
                ),
            );

            await expect(signOutEverywhere()).rejects.toThrow("Failed to sign out");

            expect(readSession()).toStrictEqual(session);
        },
    );

    // Without Web Locks only the in-flight promise orders the refresh's write
    // after the sign-out's clear.
    mswTest(
        "an in-flight refresh does not store the microsoft session again after signOutEverywhere",
        async ({ worker }) => {
            vi.spyOn(navigator, "locks", "get").mockReturnValue(
                undefined as unknown as LockManager,
            );
            const session = {
                sessionId: "flsess_ms",
                tier: "microsoft",
                uuid,
            } as const;
            writeSession(session);
            // The refresh answers only after logout has answered, so it is
            // still in flight when the sign-out starts its clear.
            const events: string[] = [];
            let loggedOut = false;
            worker.use(
                http.post(endpoint("v1/auth/logout"), () => {
                    events.push("logout");
                    loggedOut = true;
                    return new HttpResponse(null, { status: 204 });
                }),
                http.post(endpoint("v1/auth/refresh"), async () => {
                    // oxlint-disable-next-line no-unmodified-loop-condition -- the logout handler sets it
                    while (!loggedOut) {
                        // oxlint-disable-next-line no-await-in-loop -- polling the gate
                        await delay(10);
                    }
                    await delay(50);
                    events.push("refresh");
                    return HttpResponse.json(
                        makeSessionResponse("flsess_ms_fresh", "microsoft"),
                    );
                }),
                http.post(endpoint("v1/auth/anonymous/login"), () => {
                    events.push("login");
                    return HttpResponse.json(makeSessionResponse());
                }),
            );

            const refreshing = ensureSession(session);
            await signOutEverywhere();
            await refreshing;

            // The login waited for the refresh: the ordering under test ran.
            expect(events).toStrictEqual(["logout", "refresh", "login"]);
            expect(readSession()).toStrictEqual({
                sessionId: TEST_SESSION_ID,
                tier: "anonymous",
            });
        },
    );

    mswTest("adoptSession stores the session", async () => {
        const session = {
            sessionId: "flsess_ms_new",
            tier: "microsoft",
            uuid,
        } as const;

        await adoptSession(session);

        expect(readSession()).toStrictEqual(session);
    });
});

describe(useAuthSession, () => {
    mswTest("follows writes and clears in the same tab", async () => {
        const { result } = await renderHook(() => useAuthSession());
        expect(result.current).toBeNull();

        const session = {
            sessionId: "flsess_ms",
            tier: "microsoft",
            uuid: USERS.player1.uuid,
        } as const;
        writeSession(session);
        await expect.poll(() => result.current).toStrictEqual(session);

        clearSession();
        await expect.poll(() => result.current).toBeNull();
    });

    mswTest("returns a stable snapshot between writes", async () => {
        writeSession({ sessionId: "flsess_ms", tier: "microsoft" });

        const { result, rerender } = await renderHook(() => useAuthSession());
        const first = result.current;
        await rerender();

        expect(result.current).toBe(first);
    });
});
