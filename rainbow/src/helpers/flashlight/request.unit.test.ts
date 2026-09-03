import { captureException, captureMessage } from "@sentry/react";
import { test, expect, describe, vi, afterEach } from "vitest";

import { flashlightRequest, getFlashlightHeaders } from "./request.ts";

vi.mock(import("@sentry/react"), () => ({
    captureException: vi.fn<typeof captureException>(),
    captureMessage: vi.fn<typeof captureMessage>(),
}));

// The Sentry capture context is a union that does not narrow to the shape we
// pass, so read the reported body back as `unknown`.
const reportedText = (context: unknown): unknown =>
    (context as { readonly extra?: Readonly<Record<string, unknown>> } | undefined)
        ?.extra?.text;

describe(getFlashlightHeaders, () => {
    test("identifies rainbow as the client", () => {
        const headers = getFlashlightHeaders();

        expect(headers["X-Client-Type"]).toBe("rainbow");
        expect(headers["X-Client-Version"]).toBe("evergreen");
    });

    test("includes the user id", () => {
        const headers = getFlashlightHeaders();

        expect(headers["X-User-Id"]).toMatch(/^rnb_/);
    });
});

// oxlint-disable-next-line typescript/prefer-readonly-parameter-types
const mockFetch = (response: Response) => {
    const fetchMock = vi.fn<() => Promise<Response>>();
    fetchMock.mockResolvedValue(response);
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
};

describe(flashlightRequest, () => {
    afterEach(() => {
        vi.unstubAllGlobals();
        vi.clearAllMocks();
    });

    test("parses the response and sends the client headers", async () => {
        const fetchMock = mockFetch(Response.json({ hello: "world" }));

        const { data } = await flashlightRequest<{ hello: string }>("/v1/thing", {
            errorContext: "Failed to get thing",
            extra: {},
        });

        expect(data).toStrictEqual({ hello: "world" });

        const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
        expect(url).toBe("http://localhost:5173/flashlight/v1/thing");
        const headers = new Headers(init.headers);
        expect(headers.get("X-Client-Type")).toBe("rainbow");
        expect(headers.get("Content-Type")).toBe("application/json");
    });

    test("forwards init to fetch", async () => {
        const fetchMock = mockFetch(Response.json([]));

        await flashlightRequest("/v1/thing", {
            init: { method: "POST", body: JSON.stringify({ a: 1 }) },
            errorContext: "Failed to get thing",
            extra: {},
        });

        const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
        expect(init.method).toBe("POST");
        expect(init.body).toBe(JSON.stringify({ a: 1 }));
    });

    test("throws on a non-ok response", async () => {
        mockFetch(new Response("nope", { status: 500 }));

        await expect(
            flashlightRequest("/v1/thing", {
                errorContext: "Failed to get thing",
                extra: {},
            }),
        ).rejects.toThrow("Failed to get thing");
    });

    test("throws on an unparseable body", async () => {
        mockFetch(new Response("not json"));

        await expect(
            flashlightRequest("/v1/thing", {
                errorContext: "Failed to get thing",
                extra: {},
            }),
        ).rejects.toThrow("JSON");
    });

    test("sends the bearer when given one", async () => {
        const fetchMock = mockFetch(Response.json({}));

        await flashlightRequest("/v1/thing", {
            errorContext: "Failed to get thing",
            extra: {},
            bearer: "flsess_token",
        });

        const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
        expect(new Headers(init.headers).get("Authorization")).toBe(
            "Bearer flsess_token",
        );
    });

    test("reports the status on a non-ok response", async () => {
        mockFetch(new Response("nope", { status: 401 }));

        await expect(
            flashlightRequest("/v1/thing", {
                errorContext: "Failed to get thing",
                extra: {},
            }),
        ).rejects.toMatchObject({
            name: "FlashlightResponseError",
            status: 401,
        });
    });

    // The response body of /v1/auth/login and /v1/auth/refresh is a session
    // response, so any path that ships a body to Sentry can ship a bearer.
    // Redaction is unconditional rather than per-call-site: the `flsess_`
    // prefix is a hard contract on the wire (auth/api.ts throws without it),
    // so a future endpoint that returns a handle is covered for free.
    describe("handle redaction", () => {
        const HANDLE = "flsess_eyJ0eXAiOiJmbHNlc3MvMSJ9.c2lnbmF0dXJl";

        test("keeps a handle out of Sentry when a 2xx body is unparseable", async () => {
            mockFetch(new Response(`{"sessionId":"${HANDLE}"`));

            await expect(
                flashlightRequest("/v1/auth/refresh", {
                    errorContext: "Failed to refresh",
                    extra: {},
                }),
            ).rejects.toThrow("JSON");

            const [, context] = vi.mocked(captureException).mock.calls[0] ?? [];
            const text = reportedText(context);
            expect(text).not.toStrictEqual(expect.stringContaining(HANDLE));
            expect(text).toBe('{"sessionId":"flsess_<redacted>"');
        });

        test("keeps a handle out of Sentry on a non-ok body", async () => {
            mockFetch(new Response(HANDLE, { status: 500 }));

            await expect(
                flashlightRequest("/v1/auth/refresh", {
                    errorContext: "Failed to refresh",
                    extra: {},
                }),
            ).rejects.toThrow("500");

            const [, context] = vi.mocked(captureMessage).mock.calls[0] ?? [];
            expect(reportedText(context)).toBe("flsess_<redacted>");
        });

        // The thrown message reaches Sentry too, via an error boundary or an
        // unhandled rejection.
        test("keeps a handle out of the thrown error message", async () => {
            mockFetch(new Response(HANDLE, { status: 500 }));

            await expect(
                flashlightRequest("/v1/auth/refresh", {
                    errorContext: "Failed to refresh",
                    extra: {},
                }),
            ).rejects.toThrow("flsess_<redacted>");
        });

        test("leaves a body with no handle alone", async () => {
            mockFetch(new Response("upstream exploded", { status: 502 }));

            await expect(
                flashlightRequest("/v1/thing", {
                    errorContext: "Failed to get thing",
                    extra: {},
                }),
            ).rejects.toThrow("502");

            const [, context] = vi.mocked(captureMessage).mock.calls[0] ?? [];
            expect(reportedText(context)).toBe("upstream exploded");
        });
    });

    test("reads the refresh hint", async () => {
        mockFetch(Response.json({}, { headers: { "X-Auth-Refresh": "1" } }));

        const { refreshHint } = await flashlightRequest("/v1/thing", {
            errorContext: "Failed to get thing",
            extra: {},
        });

        expect(refreshHint).toBe(true);
    });
});
