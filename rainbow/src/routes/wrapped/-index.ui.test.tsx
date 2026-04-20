import { describe, expect } from "vitest";
import { USERS } from "#mocks/data.ts";
import { mswTest } from "#test/msw-test.ts";
import { renderAppRoute } from "#test/render.tsx";
import { userEvent } from "vitest/browser";
import { getWrappedYear } from "#helpers/wrapped.ts";

describe("Wrapped search page", () => {
    mswTest("renders player search input", async () => {
        const { screen } = await renderAppRoute("/wrapped");

        await expect
            .element(screen.getByRole("combobox", { name: "Search players" }))
            .toBeInTheDocument();
    });

    mswTest("contains meta description", async () => {
        await renderAppRoute("/wrapped");

        await expect
            .poll(() => {
                return document.querySelector('meta[content*="summary of a player"]');
            })
            .toBeInTheDocument();
    });

    mswTest("contains canonical link", async () => {
        await renderAppRoute("/wrapped");

        await expect
            .poll(() => {
                return document.querySelector(
                    'link[href="https://prismoverlay.com/wrapped"]',
                );
            })
            .toBeInTheDocument();
    });

    mswTest("records player visit in localStorage after search", async () => {
        const { screen } = await renderAppRoute("/wrapped");

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

    mswTest("search navigates to wrapped detail page", async () => {
        const { screen } = await renderAppRoute("/wrapped");

        const searchInput = screen.getByRole("combobox", {
            name: "Search players",
        });
        await expect.element(searchInput).toBeInTheDocument();

        await searchInput.fill(USERS.player1.username);
        await userEvent.keyboard("{Enter}");

        await expect
            .poll(() => globalThis.location.pathname)
            .toBe(`/wrapped/${USERS.player1.uuid}`);
    });

    mswTest("navigates to wrapped page with correct year param", async () => {
        const { screen } = await renderAppRoute("/wrapped");

        const searchInput = screen.getByRole("combobox", {
            name: "Search players",
        });
        await searchInput.fill(USERS.player1.username);
        await userEvent.keyboard("{Enter}");

        await expect
            .poll(() => globalThis.location.pathname)
            .toBe(`/wrapped/${USERS.player1.uuid}`);

        const search = new URLSearchParams(globalThis.location.search);
        expect(search.get("year")).toBe(getWrappedYear().toString());
    });
});
