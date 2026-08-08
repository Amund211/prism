import { test, expect, describe, vi, afterEach } from "vitest";

import { flashlightFetch, getFlashlightHeaders } from "./fetch.ts";

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

describe(flashlightFetch, () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    test("parses the response and sends the client headers", async () => {
        const fetchMock = mockFetch(Response.json({ hello: "world" }));

        const data = await flashlightFetch<{ hello: string }>("/v1/thing", {
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

        await flashlightFetch("/v1/thing", {
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
            flashlightFetch("/v1/thing", {
                errorContext: "Failed to get thing",
                extra: {},
            }),
        ).rejects.toThrow("Failed to get thing");
    });

    test("throws on an unparseable body", async () => {
        mockFetch(new Response("not json"));

        await expect(
            flashlightFetch("/v1/thing", {
                errorContext: "Failed to get thing",
                extra: {},
            }),
        ).rejects.toThrow("JSON");
    });
});
