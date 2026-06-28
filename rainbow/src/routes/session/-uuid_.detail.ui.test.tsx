import { http, HttpResponse } from "msw";
import type { SetupWorker } from "msw/browser";
import { describe, expect } from "vitest";

import { USERS } from "#mocks/data.ts";
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
});
