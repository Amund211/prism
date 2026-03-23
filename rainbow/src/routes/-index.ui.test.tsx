import { describe, expect } from "vitest";
import { USERS } from "#mocks/data.ts";
import { mswTest } from "#test/msw-test.ts";
import { stringifyPlayerVisits } from "#contexts/PlayerVisits/helpers.ts";
import { renderAppRoute } from "#test/render.tsx";
import { userEvent, page } from "vitest/browser";

/**
 * Render the real app route tree navigated to a specific URL.
 * Use this for components that depend on Route.useSearch/useParams/useLoaderDeps.
 */
// Render the real app at a given route
describe("Home page", () => {
    mswTest("renders player search input", async () => {
        const { screen } = await renderAppRoute("/");

        await expect
            .element(screen.getByRole("combobox", { name: "Search players" }))
            .toBeInTheDocument();
    });

    mswTest("contains meta description about Prism Overlay", async () => {
        await renderAppRoute("/");

        await expect
            .poll(() => {
                return document.querySelector('meta[content*="Prism Overlay"]');
            })
            .toBeInTheDocument();
    });

    mswTest("contains canonical link", async () => {
        await renderAppRoute("/");

        await expect
            .poll(() => {
                return document.querySelector('link[href="https://prismoverlay.com"]');
            })
            .toBeInTheDocument();
    });

    mswTest("search brings you to session page", async () => {
        const { screen } = await renderAppRoute("/");

        const searchInput = screen.getByRole("combobox", {
            name: "Search players",
        });
        await expect.element(searchInput).toBeInTheDocument();

        await searchInput.fill(USERS.player1.username);
        await userEvent.keyboard("{Enter}");

        await expect
            .poll(() => window.location.pathname)
            .toBe(`/session/${USERS.player1.uuid}`);

        await expect
            .element(
                screen.getByRole("heading", {
                    name: `${USERS.player1.username}'s session stats`,
                }),
            )
            .toBeInTheDocument();
    });

    mswTest("search sets default search params on navigation", async () => {
        const { screen } = await renderAppRoute("/");

        const searchInput = screen.getByRole("combobox", {
            name: "Search players",
        });
        await searchInput.fill(USERS.player1.username);
        await userEvent.keyboard("{Enter}");

        await expect
            .poll(() => window.location.pathname)
            .toBe(`/session/${USERS.player1.uuid}`);

        const search = new URLSearchParams(window.location.search);
        expect(search.get("gamemode")).toBe("overall");
        expect(search.get("stat")).toBe("fkdr");
        expect(search.get("variantSelection")).toBe("both");
        expect(search.get("sessionTableMode")).toBe("total");
        expect(search.get("showExtrapolatedSessions")).toBe("false");
    });

    mswTest("search records player visit in localStorage", async () => {
        const { screen } = await renderAppRoute("/");

        const searchInput = screen.getByRole("combobox", {
            name: "Search players",
        });
        await searchInput.fill(USERS.player1.username);
        await userEvent.keyboard("{Enter}");

        await expect
            .poll(() => window.location.pathname)
            .toBe(`/session/${USERS.player1.uuid}`);

        // Player visit should be recorded in localStorage
        await expect
            .poll(() => {
                const stored = localStorage.getItem("playerVisits");
                return stored?.includes(USERS.player1.uuid) ?? false;
            })
            .toBe(true);
    });

    mswTest("shows no favorites when localStorage is empty", async () => {
        const { screen } = await renderAppRoute("/");

        // Search input should be present
        await expect
            .element(screen.getByRole("combobox", { name: "Search players" }))
            .toBeInTheDocument();

        // No player names should appear
        await expect
            .element(screen.getByText(USERS.player1.username))
            .not.toBeInTheDocument();
        await expect
            .element(screen.getByText(USERS.player2.username))
            .not.toBeInTheDocument();
    });

    mswTest("search with unknown username does not crash", async () => {
        const { screen } = await renderAppRoute("/");

        const searchInput = screen.getByRole("combobox", {
            name: "Search players",
        });
        await expect.element(searchInput).toBeInTheDocument();

        // Type an unknown username and submit
        await searchInput.fill("UnknownPlayerXYZ");
        await userEvent.keyboard("{Enter}");

        // The app should not crash - the search input should still be present
        await expect
            .element(screen.getByRole("combobox", { name: "Search players" }))
            .toBeInTheDocument();
    });

    describe("favorites", () => {
        const setPlayerVisited = (uuid: string) => {
            localStorage.setItem(
                "playerVisits",
                stringifyPlayerVisits({
                    [uuid]: {
                        visitedCount: 1,
                        lastVisited: new Date(),
                    },
                }),
            );
        };

        mswTest("displays up to 5 favorites", async () => {
            // Set 6 player visits - only 5 should render
            const visits: Record<string, { visitedCount: number; lastVisited: Date }> =
                {};
            const allPlayers = [
                USERS.player1,
                USERS.player2,
                USERS.player3,
                USERS.player4,
                USERS.player5,
                USERS.player6,
            ];
            for (const player of allPlayers) {
                visits[player.uuid] = {
                    visitedCount: 1,
                    lastVisited: new Date(),
                };
            }
            localStorage.setItem("playerVisits", stringifyPlayerVisits(visits));

            const { screen } = await renderAppRoute("/");

            // First 5 should be visible
            await expect
                .element(screen.getByText(USERS.player1.username))
                .toBeInTheDocument();
            await expect
                .element(screen.getByText(USERS.player2.username))
                .toBeInTheDocument();

            // Count total favorite buttons - should be at most 5
            await expect
                .poll(() => {
                    const buttons = document.querySelectorAll(
                        '[id^="delete-favorite-"]',
                    );
                    return buttons.length;
                })
                .toBeLessThanOrEqual(5);
        });

        mswTest(
            "displays favorites when playerVisits are in localStorage",
            async () => {
                setPlayerVisited(USERS.player1.uuid);

                const { screen } = await renderAppRoute("/");

                await expect
                    .element(screen.getByText(USERS.player1.username))
                    .toBeInTheDocument();
            },
        );

        mswTest("clicking favorite navigates to session page", async () => {
            setPlayerVisited(USERS.player1.uuid);

            const { screen } = await renderAppRoute("/");

            const favorite = screen.getByText(USERS.player1.username);

            await expect.element(favorite).toBeInTheDocument();

            await favorite.click();

            await expect
                .poll(() => window.location.pathname)
                .toBe(`/session/${USERS.player1.uuid}`);

            const search = new URLSearchParams(window.location.search);
            expect(search.get("gamemode")).toBe("overall");
            expect(search.get("stat")).toBe("fkdr");
            expect(search.get("timeIntervalDefinition")).toBe(
                JSON.stringify({ type: "contained" }),
            );
            expect(search.get("variantSelection")).toBe("both");
            expect(search.get("sessionTableMode")).toBe("total");
            expect(search.get("showExtrapolatedSessions")).toBe("false");

            await expect
                .element(
                    screen.getByRole("heading", {
                        name: `${USERS.player1.username}'s session stats`,
                    }),
                )
                .toBeInTheDocument();
        });

        mswTest("renders delete button with correct aria-label", async () => {
            setPlayerVisited(USERS.player1.uuid);

            const { screen } = await renderAppRoute("/");

            await expect
                .element(
                    screen.getByLabelText(
                        `Remove ${USERS.player1.username} from favorites`,
                    ),
                )
                .toBeInTheDocument();
        });

        mswTest(
            "removes favorite from localStorage when delete button is clicked",
            async () => {
                setPlayerVisited(USERS.player1.uuid);

                const { screen } = await renderAppRoute("/");

                await expect
                    .element(screen.getByText(USERS.player1.username))
                    .toBeInTheDocument();

                const deleteButtonIcon = screen.getByLabelText(
                    `Remove ${USERS.player1.username} from favorites`,
                );

                await expect.element(deleteButtonIcon).toBeInTheDocument();
                await deleteButtonIcon.click();

                await expect
                    .element(screen.getByText(USERS.player1.username))
                    .not.toBeInTheDocument();
                await expect.element(deleteButtonIcon).not.toBeInTheDocument();

                const stored = localStorage.getItem("playerVisits");
                expect(stored).toStrictEqual("{}");
            },
        );

        mswTest("currentUser is shown first in favorites list", async () => {
            await page.viewport(1280, 720);

            // Set player2 as visited first, then set player1 as currentUser
            const visits: Record<string, { visitedCount: number; lastVisited: Date }> =
                {};
            visits[USERS.player2.uuid] = {
                visitedCount: 5,
                lastVisited: new Date(),
            };
            visits[USERS.player1.uuid] = {
                visitedCount: 1,
                lastVisited: new Date(Date.now() - 100000),
            };
            localStorage.setItem("playerVisits", stringifyPlayerVisits(visits));
            localStorage.setItem("currentUser", USERS.player1.uuid);

            await renderAppRoute("/");

            // The first favorite button should contain the currentUser (player1)
            await expect
                .poll(() => {
                    const buttons = document.querySelectorAll(
                        '[id^="delete-favorite-"]',
                    );
                    return buttons.length > 0 ? buttons[0].id : undefined;
                })
                .toBe(`delete-favorite-${USERS.player1.uuid}`);
        });

        mswTest("player head images render for favorites", async () => {
            setPlayerVisited(USERS.player1.uuid);

            await renderAppRoute("/");

            await expect
                .poll(() => {
                    return document.querySelector(`img[src*="${USERS.player1.uuid}"]`);
                })
                .toBeInTheDocument();
        });
    });
});
