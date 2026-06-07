import { http, HttpResponse } from "msw";
import { describe, expect } from "vitest";
import { userEvent, page } from "vitest/browser";

import { stringifyPlayerVisits } from "#contexts/PlayerVisits/helpers.ts";
import { env } from "#env.ts";
import { USERS } from "#mocks/data.ts";
import { worker } from "#mocks/worker.ts";
import { mswTest } from "#test/msw-test.ts";
import { renderAppRoute } from "#test/render.tsx";

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

    mswTest("renders downloads banner linking to downloads page", async () => {
        const { screen } = await renderAppRoute("/");

        const downloadLink = screen.getByRole("link", { name: "Download" });
        await expect.element(downloadLink).toBeInTheDocument();

        await downloadLink.click();

        await expect.poll(() => globalThis.location.pathname).toBe("/downloads");
    });

    mswTest("dismissing downloads banner stores it in localStorage", async () => {
        const { screen } = await renderAppRoute("/");

        const closeButton = screen.getByRole("button", { name: "Close" });
        await expect.element(closeButton).toBeInTheDocument();

        await closeButton.click();

        await expect
            .element(screen.getByRole("link", { name: "Download" }))
            .not.toBeInTheDocument();
        expect(localStorage.getItem("downloadsBannerDismissed")).toBe("true");
    });

    mswTest("downloads banner stays hidden when dismissed", async () => {
        localStorage.setItem("downloadsBannerDismissed", "true");

        const { screen } = await renderAppRoute("/");

        // The rest of the page should render without the banner
        await expect
            .element(screen.getByRole("combobox", { name: "Search players" }))
            .toBeInTheDocument();
        await expect
            .element(screen.getByRole("link", { name: "Download" }))
            .not.toBeInTheDocument();
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
            .poll(() => globalThis.location.pathname)
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
            .poll(() => globalThis.location.pathname)
            .toBe(`/session/${USERS.player1.uuid}`);

        const search = new URLSearchParams(globalThis.location.search);
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
            .poll(() => globalThis.location.pathname)
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
                .poll(() => globalThis.location.pathname)
                .toBe(`/session/${USERS.player1.uuid}`);

            const search = new URLSearchParams(globalThis.location.search);
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
                expect(stored).toBe("{}");
            },
        );

        mswTest("currentUser is shown first in favorites list", async () => {
            await page.viewport(1280, 720);

            // Set player2 as visited first, then set player1 as currentUser
            const visits: Record<string, { visitedCount: number; lastVisited: Date }> =
                {
                    [USERS.player2.uuid]: {
                        visitedCount: 5,
                        lastVisited: new Date(),
                    },
                    [USERS.player1.uuid]: {
                        visitedCount: 1,
                        lastVisited: new Date(Date.now() - 100_000),
                    },
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

    describe("search dropdown", () => {
        const setKnownAliases = (
            ...users: readonly { readonly uuid: string; readonly username: string }[]
        ) => {
            localStorage.setItem(
                "knownAliases",
                JSON.stringify(
                    Object.fromEntries(
                        users.map((user) => [
                            user.uuid,
                            [
                                {
                                    username: user.username,
                                    lastResolved: new Date().toISOString(),
                                },
                            ],
                        ]),
                    ),
                ),
            );
        };

        mswTest(
            "lists known players and selecting one from the dropdown navigates",
            async () => {
                // No playerVisits are seeded, so the only place these usernames can
                // appear is the (virtualized) search dropdown.
                setKnownAliases(USERS.player1, USERS.player2);

                const { screen } = await renderAppRoute("/");

                const searchInput = screen.getByRole("combobox", {
                    name: "Search players",
                });
                await searchInput.click();
                await userEvent.keyboard("{ArrowDown}");

                const option = screen.getByText(USERS.player1.username);
                await expect.element(option).toBeInTheDocument();

                await option.click();

                await expect
                    .poll(() => globalThis.location.pathname)
                    .toBe(`/session/${USERS.player1.uuid}`);
            },
        );

        // Build a known-alias history far larger than the listbox's visible window
        // so most rows are never mounted unless the virtualizer scrolls to them.
        const makeManyUsers = (count: number) =>
            Array.from({ length: count }, (_, index) => {
                const hex = index.toString(16).padStart(32, "0");
                const uuid = `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(
                    12,
                    16,
                )}-${hex.slice(16, 20)}-${hex.slice(20)}`;
                return {
                    uuid,
                    username: `VirtualPlayer${index.toString().padStart(2, "0")}`,
                };
            });

        const optionElements = () => [
            ...document.querySelectorAll<HTMLElement>('[role="option"]'),
        ];

        mswTest(
            "virtualizes the listbox and scrolls an off-screen option into view to select it",
            async () => {
                const users = makeManyUsers(30);
                // Resolve usernames for the synthetic uuids straight from the mock
                // API (only the rows the virtualizer actually mounts hit this).
                worker.use(
                    http.get(
                        `${env.VITE_FLASHLIGHT_URL}/v1/account/uuid/:uuid`,
                        ({ params }) => {
                            const user = users.find((u) => u.uuid === params.uuid);
                            if (user === undefined) {
                                // Fall through to the default handler.
                                return undefined;
                            }
                            return HttpResponse.json({
                                success: true,
                                username: user.username,
                                uuid: user.uuid,
                            });
                        },
                    ),
                );
                setKnownAliases(...users);

                const { screen } = await renderAppRoute("/");

                const searchInput = screen.getByRole("combobox", {
                    name: "Search players",
                });
                await searchInput.click();
                await userEvent.keyboard("{ArrowDown}");

                // Wait for the dropdown to render, then assert virtualization: far
                // fewer rows are mounted than the 30 seeded options.
                await expect.poll(() => optionElements().length).toBeGreaterThan(0);
                expect(optionElements().length).toBeLessThan(users.length);

                // Remember which rows the initial window mounted so we can prove the
                // option we end up on was off-screen and only mounted after scrolling.
                const initialOptionIds = new Set(
                    optionElements().map((element) => element.id),
                );

                // MUI marks the highlighted option with the Mui-focused class.
                const highlightedOption = () =>
                    optionElements().find((element) =>
                        element.classList.contains("Mui-focused"),
                    );

                // Arrow down until the highlight lands on a row that was NOT in the
                // initial window — that row only exists in the DOM because scrollToKey
                // scrolled the virtualizer to it, so this drives the dropdown the way
                // a user would. We wait for each keypress to settle before the next:
                // MUI resolves the next option via a DOM query (data-option-index), so
                // pressing faster than react-window can mount the next row makes it
                // clamp the highlight back onto a mounted row.
                let highlightedName = "";
                for (let step = 0; step < 30; step += 1) {
                    const option = highlightedOption();
                    if (option !== undefined && !initialOptionIds.has(option.id)) {
                        highlightedName = option.textContent?.trim() ?? "";
                        break;
                    }
                    const previousId = option?.id;
                    // oxlint-disable-next-line eslint/no-await-in-loop
                    await userEvent.keyboard("{ArrowDown}");
                    // oxlint-disable-next-line eslint/no-await-in-loop
                    await expect
                        .poll(() => highlightedOption()?.id)
                        .not.toBe(previousId);
                }

                expect(highlightedName).toMatch(/^VirtualPlayer\d{2}$/);

                const highlightedUser = users.find(
                    (user) => user.username === highlightedName,
                );
                expect(highlightedUser).toBeDefined();

                // Selecting the scrolled-in option with the keyboard navigates,
                // proving off-screen options stay reachable under virtualization.
                await userEvent.keyboard("{Enter}");

                await expect
                    .poll(() => globalThis.location.pathname)
                    .toBe(`/session/${highlightedUser?.uuid}`);
            },
        );
    });
});
