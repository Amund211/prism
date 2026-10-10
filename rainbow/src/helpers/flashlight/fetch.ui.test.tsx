import { captureMessage } from "@sentry/react";
import type { captureException } from "@sentry/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, vi } from "vitest";

import { makeSessionResponse } from "#mocks/data.ts";
import { mswTest } from "#test/msw-test.ts";

import { writeSession } from "./auth/storage.ts";
import { flashlightFetch } from "./fetch.ts";

vi.mock(import("@sentry/react"), () => ({
    captureException: vi.fn<typeof captureException>(),
    captureMessage: vi.fn<typeof captureMessage>(),
}));

const endpoint = (path: string) => `http://localhost:5173/flashlight/${path}`;

const fetchThing = async () =>
    flashlightFetch("/v1/thing", {
        errorContext: "Failed to get thing",
        extra: {},
        expectedStatuses: [403],
    });

describe(flashlightFetch, () => {
    afterEach(() => {
        vi.clearAllMocks();
    });

    mswTest("does not report an expected status", async ({ worker }) => {
        writeSession({ sessionId: "flsess_a", tier: "anonymous" });
        worker.use(
            http.get(
                endpoint("v1/thing"),
                () => new HttpResponse("forbidden", { status: 403 }),
            ),
        );

        await expect(fetchThing()).rejects.toMatchObject({ status: 403 });

        expect(captureMessage).not.toHaveBeenCalled();
    });

    mswTest("does not report an expected status on the retry", async ({ worker }) => {
        writeSession({ sessionId: "flsess_stale", tier: "anonymous" });
        worker.use(
            http.post(endpoint("v1/auth/refresh"), () =>
                HttpResponse.json(makeSessionResponse("flsess_fresh")),
            ),
            http.get(endpoint("v1/thing"), ({ request }) =>
                request.headers.get("Authorization") === "Bearer flsess_stale"
                    ? new HttpResponse(null, { status: 401 })
                    : new HttpResponse("forbidden", { status: 403 }),
            ),
        );

        await expect(fetchThing()).rejects.toMatchObject({ status: 403 });

        expect(captureMessage).not.toHaveBeenCalled();
    });
});
