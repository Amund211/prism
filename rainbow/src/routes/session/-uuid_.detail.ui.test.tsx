import { http, HttpResponse } from "msw";
import type { SetupWorker } from "msw/browser";
import { describe, expect } from "vitest";
import { page } from "vitest/browser";

import { makePlayerDataPIT, makeSession, USERS } from "#mocks/data.ts";
import type { APISessionAtResponse } from "#queries/sessionAt.ts";
import { mswTest } from "#test/msw-test.ts";
import { renderAppRoute } from "#test/render.tsx";

describe("Session detail page", () => {
    const date = "2025-11-03T22:00:00.000Z";
    const detailUrl = `/session/${USERS.player1.uuid}/detail?date=${encodeURIComponent(date)}`;

    mswTest("renders the player banner heading with the username", async () => {
        const { screen } = await renderAppRoute(detailUrl);

        await expect
            .element(screen.getByRole("heading", { name: USERS.player1.username }))
            .toBeInTheDocument();
    });

    mswTest("renders the share button", async () => {
        const { screen } = await renderAppRoute(detailUrl);

        await expect
            .element(screen.getByRole("button", { name: "Share" }))
            .toBeInTheDocument();
    });

    mswTest("renders the KPI row labels", async () => {
        const { screen } = await renderAppRoute(detailUrl);

        // `exact` so "Session FKDR" doesn't also match the chart's
        // "Session FKDR after each game …" subtitle.
        await expect
            .element(screen.getByText("Win rate", { exact: true }))
            .toBeInTheDocument();
        await expect
            .element(screen.getByText("Session FKDR", { exact: true }))
            .toBeInTheDocument();
        await expect
            .element(screen.getByText("Stars gained", { exact: true }))
            .toBeInTheDocument();
    });

    mswTest("renders the main section cards", async () => {
        const { screen } = await renderAppRoute(detailUrl);

        await expect.element(screen.getByText("Game-by-game")).toBeInTheDocument();
        await expect.element(screen.getByText("FKDR trajectory")).toBeInTheDocument();
        await expect.element(screen.getByText("By gamemode")).toBeInTheDocument();
        await expect.element(screen.getByText("Milestones")).toBeInTheDocument();
        await expect.element(screen.getByText("Highlights")).toBeInTheDocument();
    });

    mswTest("normalizes the URL date to the session start", async () => {
        // The mock session-at handler starts the session an hour before the
        // requested time; the page rewrites `date` to that canonical start.
        await renderAppRoute(detailUrl);

        await expect
            .poll(() => {
                const param = new URLSearchParams(globalThis.location.search).get(
                    "date",
                );
                return param !== null && param !== date;
            })
            .toBe(true);
    });

    mswTest("expands a game tile into its detail row on click", async () => {
        const { screen } = await renderAppRoute(detailUrl);

        // Wait for the momentum strip to render, then click the first game tile.
        // `.first()` disambiguates it from the identically-labelled chart axis
        // tick, which renders later in the DOM.
        const tile = screen.getByText("G1").first();
        await expect.element(tile).toBeInTheDocument();
        await tile.click();

        // The expanded detail row shows a per-game stat grid whose "FINAL KILLS"
        // label appears nowhere else on the page (the tile now shares the "G1"
        // label with the detail title, so assert on a detail-only element).
        await expect.element(screen.getByText("FINAL KILLS")).toBeInTheDocument();
    });

    mswTest("expands a multi-game gap tile into a per-gamemode breakdown", async () => {
        const { screen } = await renderAppRoute(detailUrl);

        // The mock's last segment covers three games that can't be attributed
        // individually — a solo win, a fours loss and one in a mode only
        // `overall` reflects — so it's numbered G4-6 and dotted for all three.
        const tile = screen.getByText("G4-6").first();
        await expect.element(tile).toBeInTheDocument();
        await expect
            .element(screen.getByLabelText("Modes played: Solo, Fours, Other"))
            .toBeInTheDocument();

        await tile.click();

        // "RECORD" is the wins/losses column, which only the per-mode rows have.
        await expect.element(screen.getByText("RECORD").first()).toBeInTheDocument();
        await expect.element(screen.getByText("Other").first()).toBeInTheDocument();
    });

    mswTest(
        "shows the no-session empty state when session-at returns null",
        async ({ worker }: { readonly worker: SetupWorker }) => {
            worker.use(
                http.post("http://localhost:5173/flashlight/v1/session-at", () => {
                    return HttpResponse.json({ session: null, games: [] });
                }),
            );

            const { screen } = await renderAppRoute(detailUrl);

            await expect
                .element(screen.getByText("No session yet"))
                .toBeInTheDocument();
        },
    );

    mswTest(
        "long sessions scroll the game strip instead of the page",
        async ({ worker }: { readonly worker: SetupWorker }) => {
            const { uuid } = USERS.player1;
            const start = new Date(date);
            // Enough games that the strip's `minmax(120px, 1fr)` columns exceed
            // the width left over next to the desktop sidebar.
            const gameCount = 12;
            const pits = Array.from({ length: gameCount + 1 }, (_, index) =>
                makePlayerDataPIT(
                    uuid,
                    new Date(start.getTime() + index * 10 * 60 * 1000).toISOString(),
                    index + 1,
                ),
            );

            worker.use(
                http.post("http://localhost:5173/flashlight/v1/session-at", () => {
                    const response: APISessionAtResponse = {
                        session: makeSession(
                            uuid,
                            pits[0].queriedAt,
                            pits[gameCount].queriedAt,
                        ),
                        games: Array.from({ length: gameCount }, (_, index) => ({
                            start: pits[index],
                            end: pits[index + 1],
                            game: {
                                gamemode: "doubles",
                                outcome: "win",
                                finalKills: 5,
                                finalDeath: true,
                                bedsBroken: 1,
                                bedLost: false,
                                kills: 12,
                                deaths: 4,
                                experience: 2400,
                            },
                        })),
                    };
                    return HttpResponse.json(response);
                }),
            );

            // Wide enough for the permanent sidebar to be shown.
            await page.viewport(1280, 720);
            const { screen } = await renderAppRoute(detailUrl);

            const tile = screen.getByText("G1").first();
            await expect.element(tile).toBeInTheDocument();

            // The page itself must not scroll sideways ...
            const { documentElement } = document;
            await expect
                .poll(() => documentElement.scrollWidth - documentElement.clientWidth)
                .toBe(0);

            // ... the strip holding the tiles does, so the later games stay
            // reachable rather than being clipped away. It is the only
            // horizontally scrollable container inside `<main>` (the sidebar
            // has one too, hence the scoping).
            const strip = [
                ...(document.querySelector("main")?.querySelectorAll("div") ?? []),
            ].find(
                (element) => globalThis.getComputedStyle(element).overflowX === "auto",
            );
            expect(strip).toBeDefined();
            expect(strip?.scrollWidth).toBeGreaterThan(strip?.clientWidth ?? 0);
        },
    );
});
