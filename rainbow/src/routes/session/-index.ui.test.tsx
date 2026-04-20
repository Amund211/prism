import { describe, expect } from "vitest";
import { USERS } from "#mocks/data.ts";
import { mswTest } from "#test/msw-test.ts";
import { renderAppRoute } from "#test/render.tsx";
import { userEvent } from "vitest/browser";

describe("Session search page", () => {
    mswTest("renders player search input", async () => {
        const { screen } = await renderAppRoute("/session");

        await expect
            .element(screen.getByRole("combobox", { name: "Search players" }))
            .toBeInTheDocument();
    });

    mswTest("contains meta description", async () => {
        await renderAppRoute("/session");

        await expect
            .poll(() => {
                return document.querySelector('meta[content*="session stats"]');
            })
            .toBeInTheDocument();
    });

    mswTest("contains canonical link", async () => {
        await renderAppRoute("/session");

        await expect
            .poll(() => {
                return document.querySelector(
                    'link[href="https://prismoverlay.com/session"]',
                );
            })
            .toBeInTheDocument();
    });

    mswTest("records player visit in localStorage after search", async () => {
        const { screen } = await renderAppRoute("/session");

        const searchInput = screen.getByRole("combobox", {
            name: "Search players",
        });
        await expect.element(searchInput).toBeInTheDocument();

        await searchInput.fill(USERS.player1.username);
        await userEvent.keyboard("{Enter}");

        await expect
            .poll(() => {
                const stored = localStorage.getItem("playerVisits");
                return stored?.includes(USERS.player1.uuid) ?? false;
            })
            .toBe(true);
    });

    mswTest("search navigates to session detail page", async () => {
        const { screen } = await renderAppRoute("/session");

        const searchInput = screen.getByRole("combobox", {
            name: "Search players",
        });
        await expect.element(searchInput).toBeInTheDocument();

        await searchInput.fill(USERS.player1.username);
        await userEvent.keyboard("{Enter}");

        await expect
            .poll(() => globalThis.location.pathname)
            .toBe(`/session/${USERS.player1.uuid}`);
    });

    mswTest("search with UUID directly navigates to session page", async () => {
        const { screen } = await renderAppRoute("/session");

        const searchInput = screen.getByRole("combobox", {
            name: "Search players",
        });
        await expect.element(searchInput).toBeInTheDocument();

        await searchInput.fill(USERS.player1.uuid);
        await userEvent.keyboard("{Enter}");

        await expect
            .poll(() => globalThis.location.pathname)
            .toBe(`/session/${USERS.player1.uuid}`);
    });

    mswTest("navigating sets default search params", async () => {
        const { screen } = await renderAppRoute("/session");

        const searchInput = screen.getByRole("combobox", {
            name: "Search players",
        });
        await searchInput.fill(USERS.player1.username);
        await userEvent.keyboard("{Enter}");

        await expect
            .poll(() => globalThis.location.pathname)
            .toBe(`/session/${USERS.player1.uuid}`);

        const search = new URLSearchParams(globalThis.location.search);
        expect(search.get("gamemode")).toBe("overall");
        expect(search.get("stat")).toBe("fkdr");
        expect(search.get("sessionTableMode")).toBe("total");
        expect(search.get("showExtrapolatedSessions")).toBe("false");
    });
});
