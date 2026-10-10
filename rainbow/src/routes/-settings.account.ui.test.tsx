import { delay, http, HttpResponse } from "msw";
import { describe, expect } from "vitest";
import { userEvent } from "vitest/browser";

import { readSession, writeSession } from "#helpers/flashlight/auth/storage.ts";
import { makeSessionResponse, TEST_SESSION_ID, USERS } from "#mocks/data.ts";
import { mswTest } from "#test/msw-test.ts";
import { renderAppRoute } from "#test/render.tsx";

const endpoint = (path: string) => `http://localhost:5173/flashlight/${path}`;

const { uuid, username } = USERS.player1;
const microsoftSession = { sessionId: "flsess_ms", tier: "microsoft", uuid } as const;

describe("Settings account section", () => {
    mswTest("an anonymous user sees the sign-in button", async () => {
        writeSession({ sessionId: TEST_SESSION_ID, tier: "anonymous" });

        const { screen } = await renderAppRoute("/settings");

        await expect
            .element(screen.getByRole("button", { name: "Sign in with Microsoft" }))
            .toBeInTheDocument();
    });

    mswTest("a microsoft session shows the name and the sign-ins", async () => {
        writeSession(microsoftSession);

        const { screen } = await renderAppRoute("/settings");

        await expect
            .element(screen.getByText(`Signed in as ${username}`))
            .toBeInTheDocument();
        await expect.element(screen.getByText("Browser")).toBeInTheDocument();
        await expect
            .element(screen.getByRole("button", { name: "Sign out everywhere" }))
            .toBeInTheDocument();
        await expect
            .element(screen.getByRole("button", { name: "Sign in with Microsoft" }))
            .not.toBeInTheDocument();
    });

    mswTest("a microsoft session without a uuid shows a generic line", async () => {
        writeSession({ sessionId: "flsess_ms", tier: "microsoft" });

        const { screen } = await renderAppRoute("/settings");

        await expect
            .element(screen.getByText("Signed in with Microsoft"))
            .toBeInTheDocument();
    });

    mswTest("labels each client type", async ({ worker }) => {
        writeSession(microsoftSession);
        worker.use(
            http.get(endpoint("v1/auth/credentials"), () =>
                HttpResponse.json({
                    credentials: [
                        {
                            clientType: "prism",
                            createdAt: "2026-10-02T12:00:00.000000Z",
                            lastUsedAt: "2026-10-09T12:00:00.000000Z",
                        },
                        {
                            clientType: "rainbow",
                            createdAt: "2026-10-01T12:00:00.000000Z",
                            lastUsedAt: "2026-10-10T12:00:00.000000Z",
                        },
                    ],
                }),
            ),
        );

        const { screen } = await renderAppRoute("/settings");

        await expect.element(screen.getByText("Prism overlay")).toBeInTheDocument();
        await expect.element(screen.getByText("Browser")).toBeInTheDocument();
    });

    mswTest(
        "a lapsed bearer refreshes and retries the sign-ins without an error",
        async ({ worker }) => {
            writeSession({ sessionId: "flsess_ms_stale", tier: "microsoft", uuid });
            const bearers: (string | null)[] = [];
            worker.use(
                http.post(endpoint("v1/auth/refresh"), () =>
                    HttpResponse.json(
                        makeSessionResponse("flsess_ms_fresh", "microsoft"),
                    ),
                ),
                http.get(endpoint("v1/auth/credentials"), ({ request }) => {
                    const bearer = request.headers.get("Authorization");
                    bearers.push(bearer);
                    expect(request.credentials).not.toBe("include");
                    if (bearer === "Bearer flsess_ms_stale") {
                        return new HttpResponse("unauthorized", { status: 401 });
                    }
                    return HttpResponse.json({
                        credentials: [
                            {
                                clientType: "rainbow",
                                createdAt: "2026-10-01T12:00:00.000000Z",
                                lastUsedAt: "2026-10-10T12:00:00.000000Z",
                            },
                        ],
                    });
                }),
            );

            const { screen } = await renderAppRoute("/settings");

            await expect.element(screen.getByText("Browser")).toBeInTheDocument();
            await expect
                .element(screen.getByText("Could not load your sign-ins."))
                .not.toBeInTheDocument();
            expect(bearers).toStrictEqual([
                "Bearer flsess_ms_stale",
                "Bearer flsess_ms_fresh",
            ]);
        },
    );

    mswTest("a credentials 403 hides the list without crashing", async ({ worker }) => {
        writeSession(microsoftSession);
        worker.use(
            http.get(
                endpoint("v1/auth/credentials"),
                () => new HttpResponse("Sign in with Microsoft", { status: 403 }),
            ),
        );

        const { screen } = await renderAppRoute("/settings");

        await expect
            .element(screen.getByText(`Signed in as ${username}`))
            .toBeInTheDocument();
        await expect
            .element(screen.getByText("Active sign-ins"))
            .not.toBeInTheDocument();
        await expect
            .element(screen.getByText("Could not load your sign-ins."))
            .not.toBeInTheDocument();
    });

    mswTest("a credentials 500 shows an error", async ({ worker }) => {
        writeSession(microsoftSession);
        worker.use(
            http.get(
                endpoint("v1/auth/credentials"),
                () => new HttpResponse("nope", { status: 500 }),
            ),
        );

        const { screen } = await renderAppRoute("/settings");

        await expect
            .element(screen.getByText("Could not load your sign-ins."))
            .toBeInTheDocument();
    });

    mswTest(
        "sign out everywhere asks first, calls logout and ends anonymous",
        async ({ worker }) => {
            writeSession(microsoftSession);
            let logouts = 0;
            worker.use(
                http.post(endpoint("v1/auth/logout"), () => {
                    logouts++;
                    return new HttpResponse(null, { status: 204 });
                }),
            );

            const { screen } = await renderAppRoute("/settings");

            await screen.getByRole("button", { name: "Sign out everywhere" }).click();
            await expect
                .element(
                    screen.getByText(/also signs out every Prism overlay and browser/),
                )
                .toBeInTheDocument();
            expect(logouts).toBe(0);

            await screen.getByRole("button", { name: "Sign out", exact: true }).click();

            await expect
                .element(screen.getByRole("button", { name: "Sign in with Microsoft" }))
                .toBeInTheDocument();
            expect(logouts).toBe(1);
            await expect
                .poll(() => readSession())
                .toStrictEqual({
                    sessionId: TEST_SESSION_ID,
                    tier: "anonymous",
                });
        },
    );

    mswTest("cancelling the confirm dialog keeps the session", async ({ worker }) => {
        writeSession(microsoftSession);
        let logouts = 0;
        worker.use(
            http.post(endpoint("v1/auth/logout"), () => {
                logouts++;
                return new HttpResponse(null, { status: 204 });
            }),
        );

        const { screen } = await renderAppRoute("/settings");

        await screen.getByRole("button", { name: "Sign out everywhere" }).click();
        await screen.getByRole("button", { name: "Cancel" }).click();

        await expect
            .element(screen.getByRole("button", { name: "Cancel" }))
            .not.toBeInTheDocument();
        expect(logouts).toBe(0);
        expect(readSession()).toStrictEqual(microsoftSession);
    });

    mswTest("the dialog cannot be closed while signing out", async ({ worker }) => {
        writeSession(microsoftSession);
        let released = false;
        worker.use(
            http.post(endpoint("v1/auth/logout"), async () => {
                // oxlint-disable-next-line no-unmodified-loop-condition -- the test sets it
                while (!released) {
                    // oxlint-disable-next-line no-await-in-loop -- polling the gate
                    await delay(10);
                }
                return new HttpResponse(null, { status: 204 });
            }),
        );

        const { screen } = await renderAppRoute("/settings");

        await screen.getByRole("button", { name: "Sign out everywhere" }).click();
        await screen.getByRole("button", { name: "Sign out", exact: true }).click();

        await expect
            .element(screen.getByRole("button", { name: "Cancel" }))
            .toBeDisabled();
        await userEvent.keyboard("{Escape}");
        await expect.element(screen.getByRole("dialog")).toBeInTheDocument();

        released = true;
        await expect
            .element(screen.getByRole("button", { name: "Sign in with Microsoft" }))
            .toBeInTheDocument();
        // Let the anonymous login commit, or it overwrites the next test's
        // session.
        await expect.poll(() => readSession()?.tier).toBe("anonymous");
    });

    mswTest(
        "another account's sign-ins are not shown from the cache",
        async ({ worker }) => {
            writeSession(microsoftSession);
            let calls = 0;
            worker.use(
                http.get(endpoint("v1/auth/credentials"), async () => {
                    calls++;
                    if (calls > 1) {
                        await delay("infinite");
                    }
                    return HttpResponse.json({
                        credentials: [
                            {
                                clientType: "prism",
                                createdAt: "2026-10-01T12:00:00.000000Z",
                                lastUsedAt: "2026-10-10T12:00:00.000000Z",
                            },
                        ],
                    });
                }),
            );

            const { screen } = await renderAppRoute("/settings");
            await expect.element(screen.getByText("Prism overlay")).toBeInTheDocument();

            // Another tab signed in as someone else.
            writeSession({
                sessionId: "flsess_ms_other",
                tier: "microsoft",
                uuid: USERS.player2.uuid,
            });

            await expect
                .element(screen.getByText(`Signed in as ${USERS.player2.username}`))
                .toBeInTheDocument();
            await expect
                .element(screen.getByText("Prism overlay"))
                .not.toBeInTheDocument();
        },
    );

    mswTest("a logout 500 keeps the session and shows an error", async ({ worker }) => {
        writeSession(microsoftSession);
        worker.use(
            http.post(
                endpoint("v1/auth/logout"),
                () => new HttpResponse("nope", { status: 500 }),
            ),
        );

        const { screen } = await renderAppRoute("/settings");

        await screen.getByRole("button", { name: "Sign out everywhere" }).click();
        await screen.getByRole("button", { name: "Sign out", exact: true }).click();

        await expect
            .element(screen.getByText("Could not sign out. Try again."))
            .toBeInTheDocument();
        expect(readSession()).toStrictEqual(microsoftSession);
        await expect
            .element(screen.getByText(`Signed in as ${username}`))
            .toBeInTheDocument();
    });
});
