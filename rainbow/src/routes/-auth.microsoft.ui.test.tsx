import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, vi } from "vitest";

import {
    isMicrosoftCallback,
    prepareMicrosoftSignIn,
} from "#helpers/flashlight/auth/microsoft.ts";
import { readSession } from "#helpers/flashlight/auth/storage.ts";
import { makeMicrosoftSessionResponse, USERS } from "#mocks/data.ts";
import { mswTest } from "#test/msw-test.ts";
import { renderAppRoute } from "#test/render.tsx";

const endpoint = (path: string) => `http://localhost:5173/flashlight/${path}`;

const VERIFIER_KEY = "rainbow_ms_verifier";
const VERIFIER = "v".repeat(43);
const RESULT = "flresult_abc.def";

describe("startMicrosoftSignIn", () => {
    mswTest("stores the verifier and builds the start URL", async () => {
        const url = new URL(await prepareMicrosoftSignIn());

        expect(`${url.origin}${url.pathname}`).toBe(
            endpoint("v1/auth/microsoft/start"),
        );
        expect([...url.searchParams.keys()]).toStrictEqual(["return", "challenge"]);
        expect(url.searchParams.get("return")).toBe(location.origin);
        expect(url.searchParams.get("challenge")).toMatch(/^[A-Za-z0-9_-]{43}$/);
        expect(sessionStorage.getItem(VERIFIER_KEY)).toMatch(/^[A-Za-z0-9_-]{43}$/);
    });
});

describe(isMicrosoftCallback, () => {
    mswTest.for([
        ["/auth/microsoft#result=flresult_x", true],
        ["/auth/microsoft#error=no_game", true],
        ["/auth/microsoft", false],
        ["/settings#result=flresult_x", false],
    ] as const)("%s is %s", ([url, expected]) => {
        history.replaceState(history.state, "", url);

        expect(isMicrosoftCallback()).toBe(expected);
    });
});

describe("/auth/microsoft", () => {
    const { uuid } = USERS.player1;

    afterEach(() => {
        vi.restoreAllMocks();
    });

    mswTest("exchanges the result and lands on /settings", async ({ worker }) => {
        sessionStorage.setItem(VERIFIER_KEY, VERIFIER);
        const bodies: unknown[] = [];
        worker.use(
            http.post(endpoint("v1/auth/microsoft/exchange"), async ({ request }) => {
                bodies.push(await request.json());
                expect(request.credentials).toBe("include");
                return HttpResponse.json(
                    makeMicrosoftSessionResponse("flsess_ms", uuid),
                );
            }),
        );

        const { router } = await renderAppRoute(`/auth/microsoft#result=${RESULT}`);

        await expect.poll(() => router.state.location.pathname).toBe("/settings");
        expect(bodies).toStrictEqual([{ result: RESULT, verifier: VERIFIER }]);
        expect(readSession()).toStrictEqual({
            sessionId: "flsess_ms",
            tier: "microsoft",
            uuid,
        });
        expect(sessionStorage.getItem(VERIFIER_KEY)).toBeNull();
    });

    mswTest("removes the fragment from the URL", async () => {
        sessionStorage.setItem(VERIFIER_KEY, VERIFIER);

        await renderAppRoute(`/auth/microsoft#result=${RESULT}`);

        expect(location.hash).toBe("");
        expect(location.href).not.toContain(RESULT);
    });

    mswTest("sets the default player when it is unset", async () => {
        sessionStorage.setItem(VERIFIER_KEY, VERIFIER);

        const { router } = await renderAppRoute(`/auth/microsoft#result=${RESULT}`);

        await expect.poll(() => router.state.location.pathname).toBe("/settings");
        expect(localStorage.getItem("currentUser")).toBe(uuid);
    });

    mswTest("keeps a default player that is set", async () => {
        localStorage.setItem("currentUser", USERS.player2.uuid);
        sessionStorage.setItem(VERIFIER_KEY, VERIFIER);

        const { router } = await renderAppRoute(`/auth/microsoft#result=${RESULT}`);

        await expect.poll(() => router.state.location.pathname).toBe("/settings");
        expect(localStorage.getItem("currentUser")).toBe(USERS.player2.uuid);
    });

    mswTest("shows the message for an error code", async () => {
        const { screen } = await renderAppRoute(
            "/auth/microsoft#error=microsoft_error",
        );

        await expect
            .element(screen.getByText("Sign-in was cancelled."))
            .toBeInTheDocument();
        await expect
            .element(screen.getByRole("button", { name: "Try again" }))
            .toBeInTheDocument();
        expect(readSession()?.tier).not.toBe("microsoft");
    });

    mswTest.for([
        "client_not_approved",
        "no_game",
        "no_profile",
        "child_account",
        "adult_verification_required",
        "xbox_unavailable_in_region",
    ])("hides Try again for %s, which a retry cannot fix", async (code) => {
        const { screen } = await renderAppRoute(`/auth/microsoft#error=${code}`);

        await expect.element(screen.getByText(/\.$/)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Try again" }).query()).toBeNull();
    });

    mswTest("shows the expired message without a verifier", async ({ worker }) => {
        let exchanges = 0;
        worker.use(
            http.post(endpoint("v1/auth/microsoft/exchange"), () => {
                exchanges++;
                return HttpResponse.json(makeMicrosoftSessionResponse());
            }),
        );

        const { screen } = await renderAppRoute(`/auth/microsoft#result=${RESULT}`);

        await expect
            .element(screen.getByText("Sign-in expired. Try again."))
            .toBeInTheDocument();
        expect(exchanges).toBe(0);
    });

    mswTest.for([
        [401, "Sign-in expired. Try again."],
        [500, "Sign-in failed. Try again later."],
    ] as const)(
        "shows a message when the exchange returns %i",
        async ([status, message], { worker }) => {
            sessionStorage.setItem(VERIFIER_KEY, VERIFIER);
            worker.use(
                http.post(
                    endpoint("v1/auth/microsoft/exchange"),
                    () => new HttpResponse("Sign in again", { status }),
                ),
            );

            const { screen } = await renderAppRoute(`/auth/microsoft#result=${RESULT}`);

            await expect.element(screen.getByText(message)).toBeInTheDocument();
            expect(readSession()?.tier).not.toBe("microsoft");
        },
    );

    mswTest("keeps the router's history state", async () => {
        const { screen } = await renderAppRoute("/auth/microsoft#error=no_game");

        await expect.element(screen.getByText(/does not own/)).toBeInTheDocument();
        expect(location.hash).toBe("");
        // replaceState(null, ...) would drop it.
        expect(history.state).not.toBeNull();
    });

    mswTest("removes the verifier on an error callback", async () => {
        sessionStorage.setItem(VERIFIER_KEY, VERIFIER);

        const { screen } = await renderAppRoute(
            "/auth/microsoft#error=microsoft_error",
        );

        await expect
            .element(screen.getByText("Sign-in was cancelled."))
            .toBeInTheDocument();
        expect(sessionStorage.getItem(VERIFIER_KEY)).toBeNull();
    });

    mswTest("shows a new message when Try again cannot start", async () => {
        const { screen } = await renderAppRoute("/auth/microsoft#error=internal_error");
        await expect
            .element(screen.getByText("Sign-in failed. Try again later."))
            .toBeInTheDocument();
        vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
            throw new Error("quota");
        });

        await screen.getByRole("button", { name: "Try again" }).click();

        await expect
            .element(screen.getByText("Could not start the sign-in. Try again later."))
            .toBeInTheDocument();
    });

    mswTest("is not indexed", async () => {
        await renderAppRoute("/auth/microsoft#error=no_game");

        await expect
            .poll(() =>
                document.querySelector('meta[name="robots"]')?.getAttribute("content"),
            )
            .toBe("noindex");
    });
});
