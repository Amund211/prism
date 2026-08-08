import { http, HttpResponse } from "msw";
import { describe, expect } from "vitest";

import { flashlightFetch } from "#helpers/flashlight/fetch.ts";
import { makeSessionResponse, TEST_SESSION_ID } from "#mocks/data.ts";
import { mswTest } from "#test/msw-test.ts";

import { readSession, writeSession } from "./storage.ts";

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
