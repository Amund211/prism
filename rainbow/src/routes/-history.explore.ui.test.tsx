import { describe, expect } from "vitest";
import { http, HttpResponse } from "msw";
import type { SetupWorker } from "msw/browser";
import { USERS } from "#mocks/data.ts";
import { mswTest } from "#test/msw-test.ts";
import { renderAppRoute } from "#test/render.tsx";
import { userEvent } from "vitest/browser";
import { startOfDay, endOfDay } from "#intervals.ts";

describe("History Explore page", () => {
    const historyUrl = `/history/explore?uuids=${encodeURIComponent(JSON.stringify([USERS.player1.uuid]))}&gamemodes=${encodeURIComponent(JSON.stringify(["overall"]))}&stats=${encodeURIComponent(JSON.stringify(["fkdr"]))}&variantSelection=both&start=${encodeURIComponent(new Date(Date.now() - 86_400_000).toISOString())}&end=${encodeURIComponent(new Date().toISOString())}&limit=100`;

    mswTest("renders time filter chips", async () => {
        const { screen } = await renderAppRoute(historyUrl);

        await expect.element(screen.getByText("Today")).toBeInTheDocument();

        await expect.element(screen.getByText("This week")).toBeInTheDocument();

        await expect.element(screen.getByText("This month")).toBeInTheDocument();
    });

    mswTest("renders variant selection toggle", async () => {
        const { screen } = await renderAppRoute(historyUrl);

        await expect
            .element(
                screen.getByRole("group", {
                    name: "Stat chart variant selection",
                }),
            )
            .toBeInTheDocument();
    });

    mswTest("renders gamemodes selector", async () => {
        const { screen } = await renderAppRoute(historyUrl);

        await expect.element(screen.getByLabelText("Gamemodes")).toBeInTheDocument();
    });

    mswTest("renders stat selector", async () => {
        const { screen } = await renderAppRoute(historyUrl);

        await expect
            .element(screen.getByLabelText("Stat", { exact: true }))
            .toBeInTheDocument();
    });

    mswTest("renders player chip in multi-select", async () => {
        await renderAppRoute(historyUrl);

        // The player name appears as a chip in the Autocomplete multi-select
        await expect
            .poll(() => {
                return document.querySelector(".MuiChip-label");
            })
            .toBeInTheDocument();

        await expect
            .poll(() => {
                const chip = document.querySelector(".MuiChip-label");
                return chip?.textContent;
            })
            .toBe(USERS.player1.username);
    });

    mswTest("renders date pickers", async () => {
        await renderAppRoute(historyUrl);

        await expect
            .poll(() => {
                return (
                    document.querySelector('input[aria-label="Start"]') ??
                    document.querySelector('[aria-labelledby*="Start"]') ??
                    document.querySelector("label:has(+ .MuiPickersInputBase-root)")
                );
            })
            .toBeInTheDocument();
    });

    mswTest("renders chart title with stat label", async () => {
        const { screen } = await renderAppRoute(historyUrl);

        // The chart title contains the player's name and stat
        await expect
            .element(
                screen.getByText(`${USERS.player1.username}'s final kill/death ratio`),
            )
            .toBeInTheDocument();
    });

    mswTest("add and remove users in multi-select", async () => {
        const { screen } = await renderAppRoute(historyUrl);

        // Initially player1 chip should be present
        await expect
            .poll(() => {
                const chips = document.querySelectorAll(".MuiChip-label");
                return [...chips].some((c) => c.textContent === USERS.player1.username);
            })
            .toBe(true);

        // Add player2 via the input
        const input = screen.getByPlaceholder("Add players");
        await input.fill(USERS.player2.username);
        await userEvent.keyboard("{Enter}");

        // Both players should now be present
        await expect
            .poll(() => {
                const chips = document.querySelectorAll(".MuiChip-label");
                const texts = [...chips].map((c) => c.textContent);
                return (
                    texts.includes(USERS.player1.username) &&
                    texts.includes(USERS.player2.username)
                );
            })
            .toBe(true);

        // Remove player1 by clicking its chip delete button
        await expect
            .poll(() => {
                const chips = document.querySelectorAll(".MuiChip-root");
                for (const chip of chips) {
                    if (chip.textContent === USERS.player1.username) {
                        const deleteIcon = chip.querySelector(".MuiChip-deleteIcon");
                        if (deleteIcon) {
                            deleteIcon.dispatchEvent(
                                new MouseEvent("click", { bubbles: true }),
                            );
                            return true;
                        }
                    }
                }
                return false;
            })
            .toBe(true);

        // Only player2 should remain
        await expect
            .poll(() => {
                const chips = document.querySelectorAll(".MuiChip-label");
                const texts = [...chips].map((c) => c.textContent);
                return (
                    !texts.includes(USERS.player1.username) &&
                    texts.includes(USERS.player2.username)
                );
            })
            .toBe(true);
    });

    mswTest("renders multiple user chips when multiple UUIDs provided", async () => {
        const multiUserUrl = `/history/explore?uuids=${encodeURIComponent(JSON.stringify([USERS.player1.uuid, USERS.player2.uuid]))}&gamemodes=${encodeURIComponent(JSON.stringify(["overall"]))}&stats=${encodeURIComponent(JSON.stringify(["fkdr"]))}&variantSelection=both&start=${encodeURIComponent(new Date(Date.now() - 86_400_000).toISOString())}&end=${encodeURIComponent(new Date().toISOString())}&limit=100`;

        await renderAppRoute(multiUserUrl);

        // Both player names should appear as chips
        await expect
            .poll(() => {
                const chips = document.querySelectorAll(".MuiChip-label");
                const texts = [...chips].map((c) => c.textContent);
                return (
                    texts.includes(USERS.player1.username) &&
                    texts.includes(USERS.player2.username)
                );
            })
            .toBe(true);
    });

    mswTest("contains meta description", async () => {
        await renderAppRoute(historyUrl);

        await expect
            .poll(() => {
                return document.querySelector('meta[content*="Compare the stats"]');
            })
            .toBeInTheDocument();
    });

    mswTest("contains canonical link", async () => {
        await renderAppRoute(historyUrl);

        await expect
            .poll(() => {
                return document.querySelector(
                    `link[href="https://prismoverlay.com/history/explore?uuids=${encodeURIComponent(JSON.stringify([USERS.player1.uuid]))}"]`,
                );
            })
            .toBeInTheDocument();
    });

    describe("canonical link sorts uuids", () => {
        for (const uuids of [
            [USERS.player1.uuid, USERS.player2.uuid],
            [USERS.player2.uuid, USERS.player1.uuid],
        ]) {
            mswTest(`uuids=${uuids.join(", ")}`, async () => {
                const url = `/history/explore?uuids=${encodeURIComponent(JSON.stringify(uuids))}`;

                await renderAppRoute(url);

                await expect
                    .poll(() => {
                        return document.querySelector(
                            `link[href="https://prismoverlay.com/history/explore?uuids=${encodeURIComponent(
                                JSON.stringify([
                                    USERS.player1.uuid,
                                    USERS.player2.uuid,
                                ]),
                            )}"]`,
                        );
                    })
                    .toBeInTheDocument();
            });
        }
    });

    mswTest("Today chip is highlighted when date range matches today", async () => {
        const now = new Date();
        const todayUrl = `/history/explore?uuids=${encodeURIComponent(JSON.stringify([USERS.player1.uuid]))}&gamemodes=${encodeURIComponent(JSON.stringify(["overall"]))}&stats=${encodeURIComponent(JSON.stringify(["fkdr"]))}&variantSelection=both&start=${encodeURIComponent(startOfDay(now).toISOString())}&end=${encodeURIComponent(endOfDay(now).toISOString())}&limit=100`;

        await renderAppRoute(todayUrl);

        // The "Today" chip should be highlighted with primary color
        await expect
            .poll(() => {
                const chips = document.querySelectorAll(".MuiChip-root");
                for (const chip of chips) {
                    if (chip.textContent === "Today") {
                        return chip.classList.toString().includes("Primary");
                    }
                }
                return false;
            })
            .toBe(true);
    });

    mswTest(
        "session page button is disabled when multiple users selected",
        async () => {
            const multiUserUrl = `/history/explore?uuids=${encodeURIComponent(JSON.stringify([USERS.player1.uuid, USERS.player2.uuid]))}&gamemodes=${encodeURIComponent(JSON.stringify(["overall"]))}&stats=${encodeURIComponent(JSON.stringify(["fkdr"]))}&variantSelection=both&start=${encodeURIComponent(new Date(Date.now() - 86_400_000).toISOString())}&end=${encodeURIComponent(new Date().toISOString())}&limit=100`;

            await renderAppRoute(multiUserUrl);

            // The session page link button should be disabled
            await expect
                .poll(() => {
                    const button = document.querySelector(
                        '[aria-labelledby="go-to-session-page-tooltip"]',
                    );
                    return button?.hasAttribute("disabled") ?? false;
                })
                .toBe(true);
        },
    );

    mswTest(
        "session page button is enabled when single user, stat, and gamemode selected",
        async () => {
            await renderAppRoute(historyUrl);

            await expect
                .poll(() => {
                    const button = document.querySelector(
                        '[aria-labelledby="go-to-session-page-tooltip"]',
                    );
                    return button !== null && !button.hasAttribute("disabled");
                })
                .toBe(true);
        },
    );

    mswTest(
        "page renders without crashing when history API returns empty",
        async ({ worker }: { readonly worker: SetupWorker }) => {
            worker.use(
                http.post("http://localhost:5173/flashlight/v1/history", () => {
                    return HttpResponse.json([]);
                }),
            );

            const { screen } = await renderAppRoute(historyUrl);

            // Page should still render with controls available
            await expect.element(screen.getByText("Today")).toBeInTheDocument();
            await expect
                .element(screen.getByLabelText("Gamemodes"))
                .toBeInTheDocument();
        },
    );

    mswTest("clicking Today chip highlights it as active", async () => {
        // Use a date range that doesn't match "Today" so the chip starts unhighlighted
        const pastUrl = `/history/explore?uuids=${encodeURIComponent(JSON.stringify([USERS.player1.uuid]))}&gamemodes=${encodeURIComponent(JSON.stringify(["overall"]))}&stats=${encodeURIComponent(JSON.stringify(["fkdr"]))}&variantSelection=both&start=${encodeURIComponent(new Date(Date.now() - 7 * 86_400_000).toISOString())}&end=${encodeURIComponent(new Date(Date.now() - 6 * 86_400_000).toISOString())}&limit=100`;

        const { screen } = await renderAppRoute(pastUrl);

        await expect.element(screen.getByText("Today")).toBeInTheDocument();

        await screen.getByText("Today").click();

        // After clicking, the "Today" chip should become highlighted
        await expect
            .poll(() => {
                const chips = document.querySelectorAll(".MuiChip-root");
                for (const chip of chips) {
                    if (chip.textContent === "Today") {
                        return chip.classList.toString().includes("Primary");
                    }
                }
                return false;
            })
            .toBe(true);
    });

    mswTest("session page button navigates to session page when clicked", async () => {
        await renderAppRoute(historyUrl);

        // Wait for button to be enabled
        await expect
            .poll(() => {
                const button = document.querySelector(
                    '[aria-labelledby="go-to-session-page-tooltip"]',
                );
                return button !== null && !button.hasAttribute("disabled");
            })
            .toBe(true);

        const button = document.querySelector<HTMLElement>(
            '[aria-labelledby="go-to-session-page-tooltip"]',
        );
        expect(button).not.toBeNull();
        button?.click();

        await expect
            .poll(() => globalThis.location.pathname)
            .toBe(`/session/${USERS.player1.uuid}`);
    });

    mswTest("session page button navigates with correct params", async () => {
        await renderAppRoute(historyUrl);

        // Wait for button to be enabled
        await expect
            .poll(() => {
                const button = document.querySelector(
                    '[aria-labelledby="go-to-session-page-tooltip"]',
                );
                return button !== null && !button.hasAttribute("disabled");
            })
            .toBe(true);

        const button = document.querySelector<HTMLElement>(
            '[aria-labelledby="go-to-session-page-tooltip"]',
        );
        expect(button).not.toBeNull();
        button?.click();

        await expect
            .poll(() => globalThis.location.pathname)
            .toBe(`/session/${USERS.player1.uuid}`);

        // Check that the stat and gamemode are carried over
        const search = new URLSearchParams(globalThis.location.search);
        expect(search.get("stat")).toBe("fkdr");
        expect(search.get("gamemode")).toBe("overall");
    });

    mswTest("This week chip updates date range in URL", async () => {
        const { screen } = await renderAppRoute(historyUrl);

        await expect.element(screen.getByText("This week")).toBeInTheDocument();

        await screen.getByText("This week").click();

        // After clicking "This week", the chip should become highlighted
        await expect
            .poll(() => {
                const chips = document.querySelectorAll(".MuiChip-root");
                for (const chip of chips) {
                    if (chip.textContent === "This week") {
                        return chip.classList.toString().includes("Primary");
                    }
                }
                return false;
            })
            .toBe(true);
    });

    mswTest("variant selection toggle changes URL params", async () => {
        await renderAppRoute(historyUrl);

        // Click "Session" variant toggle
        await expect
            .poll(() => {
                const group = document.querySelector(
                    '[aria-label="Stat chart variant selection"]',
                );
                const sessionBtn = group?.querySelector('[value="session"]');
                if (sessionBtn) {
                    (sessionBtn as HTMLElement).click();
                    return true;
                }
                return false;
            })
            .toBe(true);

        await expect
            .poll(() =>
                new URLSearchParams(globalThis.location.search).get("variantSelection"),
            )
            .toBe("session");
    });

    mswTest("records player visits in localStorage on load", async () => {
        await renderAppRoute(historyUrl);

        await expect
            .poll(() => {
                const stored = localStorage.getItem("playerVisits");
                return stored?.includes(USERS.player1.uuid) ?? false;
            })
            .toBe(true);
    });

    mswTest("renders all time filter chips", async () => {
        const { screen } = await renderAppRoute(historyUrl);

        await expect.element(screen.getByText("Yesterday")).toBeInTheDocument();
        await expect.element(screen.getByText("Last week")).toBeInTheDocument();
        await expect.element(screen.getByText("Last month")).toBeInTheDocument();
        await expect.element(screen.getByText("This year")).toBeInTheDocument();
        await expect.element(screen.getByText("Last year")).toBeInTheDocument();
    });

    mswTest(
        "page renders controls when history API returns 500",
        async ({ worker }: { readonly worker: SetupWorker }) => {
            worker.use(
                http.post("http://localhost:5173/flashlight/v1/history", () => {
                    return HttpResponse.json({ success: false }, { status: 500 });
                }),
            );

            const { screen } = await renderAppRoute(historyUrl);

            // Page should still render with controls available despite API error
            await expect.element(screen.getByText("Today")).toBeInTheDocument();
            await expect
                .element(screen.getByLabelText("Gamemodes"))
                .toBeInTheDocument();
            await expect
                .element(screen.getByLabelText("Stat", { exact: true }))
                .toBeInTheDocument();
        },
    );

    mswTest("page renders controls when no players are in URL", async () => {
        const emptyPlayersUrl = `/history/explore?uuids=${encodeURIComponent(JSON.stringify([]))}&gamemodes=${encodeURIComponent(JSON.stringify(["overall"]))}&stats=${encodeURIComponent(JSON.stringify(["fkdr"]))}&variantSelection=both&start=${encodeURIComponent(new Date(Date.now() - 86_400_000).toISOString())}&end=${encodeURIComponent(new Date().toISOString())}&limit=100`;

        const { screen } = await renderAppRoute(emptyPlayersUrl);

        // Controls should still render even without players
        await expect.element(screen.getByText("Today")).toBeInTheDocument();
        await expect.element(screen.getByLabelText("Gamemodes")).toBeInTheDocument();
        await expect
            .element(screen.getByLabelText("Stat", { exact: true }))
            .toBeInTheDocument();
    });

    mswTest("gamemodes multi-select updates URL params", async () => {
        const { screen } = await renderAppRoute(historyUrl);

        const gamemodesSelect = screen.getByLabelText("Gamemodes");
        await expect.element(gamemodesSelect).toBeInTheDocument();

        // Open the select dropdown and click "Solo"
        await gamemodesSelect.click();
        await screen.getByRole("option", { name: "Solo" }).click();

        // Close dropdown by pressing Escape
        await userEvent.keyboard("{Escape}");

        await expect
            .poll(() => {
                const params = new URLSearchParams(globalThis.location.search);
                const gamemodes = params.get("gamemodes");
                return gamemodes?.includes("solo") ?? false;
            })
            .toBe(true);
    });

    mswTest("stat multi-select updates URL params", async () => {
        const { screen } = await renderAppRoute(historyUrl);

        const statSelect = screen.getByLabelText("Stat", { exact: true });
        await expect.element(statSelect).toBeInTheDocument();

        // Open the select dropdown and click "Wins"
        await statSelect.click();
        await screen.getByRole("option", { name: "Wins", exact: true }).click();

        // Close dropdown by pressing Escape
        await userEvent.keyboard("{Escape}");

        await expect
            .poll(() => {
                const params = new URLSearchParams(globalThis.location.search);
                const stats = params.get("stats");
                return stats?.includes("wins") ?? false;
            })
            .toBe(true);
    });

    mswTest("multiple gamemodes render correctly", async () => {
        const multiGamemodeUrl = `/history/explore?uuids=${encodeURIComponent(JSON.stringify([USERS.player1.uuid]))}&gamemodes=${encodeURIComponent(JSON.stringify(["overall", "solo"]))}&stats=${encodeURIComponent(JSON.stringify(["fkdr"]))}&variantSelection=both&start=${encodeURIComponent(new Date(Date.now() - 86_400_000).toISOString())}&end=${encodeURIComponent(new Date().toISOString())}&limit=100`;

        await renderAppRoute(multiGamemodeUrl);

        // With multiple gamemodes, both should be reflected in the page
        await expect
            .poll(() => {
                return document.body.textContent.includes("solo");
            })
            .toBe(true);
    });

    mswTest("chart title updates when multiple stats selected", async () => {
        // URL with two stats
        const multiStatUrl = `/history/explore?uuids=${encodeURIComponent(JSON.stringify([USERS.player1.uuid]))}&gamemodes=${encodeURIComponent(JSON.stringify(["overall"]))}&stats=${encodeURIComponent(JSON.stringify(["fkdr", "wins"]))}&variantSelection=both&start=${encodeURIComponent(new Date(Date.now() - 86_400_000).toISOString())}&end=${encodeURIComponent(new Date().toISOString())}&limit=100`;

        const { screen } = await renderAppRoute(multiStatUrl);

        // With multiple stats, the title should include "wins" as well
        await expect.element(screen.getByText(/wins/).first()).toBeInTheDocument();
    });
});
