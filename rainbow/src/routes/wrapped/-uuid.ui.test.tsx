import { describe, expect } from "vitest";
import { http, HttpResponse } from "msw";
import { USERS, makeWrappedResponse } from "#mocks/data.ts";
import { mswTest } from "#test/msw-test.ts";
import { renderAppRoute } from "#test/render.tsx";
import { getWrappedYear } from "#helpers/wrapped.ts";
import { userEvent } from "vitest/browser";

describe("Wrapped detail page", () => {
    const year = getWrappedYear();
    const wrappedUrl = `/wrapped/${USERS.player1.uuid}?year=${year.toString()}`;

    mswTest("renders year wrapped title", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect
            .element(screen.getByText(`${year.toString()} Wrapped`))
            .toBeInTheDocument();
    });

    mswTest("renders year subtitle", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect
            .element(
                screen.getByRole("heading", {
                    name: "A year of Bed Wars achievements",
                }),
            )
            .toBeInTheDocument();
    });

    mswTest("renders player search input", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect
            .element(screen.getByRole("combobox", { name: "Search players" }))
            .toBeInTheDocument();
    });

    mswTest("renders total sessions stat", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect.element(screen.getByRole("heading", { name: "42" })).toBeVisible();
    });

    mswTest("renders session overview section", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect
            .element(screen.getByRole("heading", { name: "Session Overview" }))
            .toBeVisible();
    });

    mswTest("renders year stats cards", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect
            .element(screen.getByRole("heading", { name: "Games Played" }).first())
            .toBeInTheDocument();
        await expect.element(screen.getByText("Wins").first()).toBeInTheDocument();
        await expect
            .element(screen.getByText("Final Kills").first())
            .toBeInTheDocument();
    });

    mswTest("renders sessions per month section", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect.element(screen.getByText("Jan").first()).toBeInTheDocument();
        await expect.element(screen.getByText("Feb").first()).toBeInTheDocument();
        await expect.element(screen.getByText("Dec").first()).toBeInTheDocument();
    });

    mswTest("renders total time stat", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect
            .element(screen.getByText("Total Time").first())
            .toBeInTheDocument();
    });

    mswTest("renders filtered out sessions stat", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect
            .element(screen.getByText("Filtered Out").first())
            .toBeInTheDocument();
    });

    mswTest("renders best sessions section", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect
            .element(screen.getByText("Highest FKDR").first())
            .toBeInTheDocument();
        await expect.element(screen.getByText("Most Wins").first()).toBeInTheDocument();
    });

    mswTest("renders Longest Session best session card", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect
            .element(screen.getByText("Longest Session").first())
            .toBeInTheDocument();
    });

    mswTest("renders Most Kills best session card", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect
            .element(screen.getByText("Most Kills").first())
            .toBeInTheDocument();
    });

    mswTest("renders Most Final Kills best session card", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect
            .element(screen.getByText("Most Final Kills").first())
            .toBeInTheDocument();
    });

    mswTest(
        "shows error state when wrapped API fails",
        async ({ worker }: { worker: import("msw/browser").SetupWorker }) => {
            worker.use(
                http.get(
                    "http://localhost:5173/flashlight/v1/wrapped/:uuid/:year",
                    () => {
                        return HttpResponse.json({ success: false }, { status: 500 });
                    },
                ),
            );

            await renderAppRoute(wrappedUrl);

            await expect
                .poll(() => {
                    return document.body.textContent.includes(
                        "Failed loading your year in review",
                    );
                })
                .toBe(true);
        },
    );

    mswTest("renders streaks section", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect
            .element(screen.getByText("Highest Ended Winstreaks").first())
            .toBeInTheDocument();
        await expect
            .element(screen.getByText("Highest Ended Final Kill Streaks").first())
            .toBeInTheDocument();
    });

    mswTest("renders average session stats section", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect
            .element(
                screen.getByRole("heading", { name: "Average Session Stats" }).first(),
            )
            .toBeInTheDocument();
        await expect
            .element(screen.getByText("Games/Session").first())
            .toBeInTheDocument();
        await expect
            .element(screen.getByText("Wins/Session").first())
            .toBeInTheDocument();
    });

    mswTest("renders flawless sessions section", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect
            .element(screen.getByText("Flawless Sessions").first())
            .toBeInTheDocument();
        // Mock data has count: 5
        await expect.element(screen.getByText("5").first()).toBeInTheDocument();
    });

    mswTest("renders session coverage section", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect
            .element(screen.getByRole("heading", { name: "Session Coverage" }).first())
            .toBeInTheDocument();
    });

    mswTest("renders play time patterns section", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect
            .element(screen.getByText(/Play Time Patterns/).first())
            .toBeInTheDocument();
    });

    mswTest("renders export summary button", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect
            .element(screen.getByText("Export Summary").first())
            .toBeInTheDocument();
    });

    mswTest("renders celebration card", async () => {
        await renderAppRoute(wrappedUrl);

        await expect
            .poll(() => {
                const elements = document.querySelectorAll('[class*="MuiTypography"]');
                return Array.from(elements).some((el) =>
                    el.textContent.includes("What a Year!"),
                );
            })
            .toBe(true);
    });

    mswTest("renders FKDR stat card", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect
            .element(screen.getByRole("heading", { name: "FKDR" }).first())
            .toBeInTheDocument();
    });

    mswTest("renders beds broken stat card", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect
            .element(screen.getByRole("heading", { name: "Beds Broken" }).first())
            .toBeInTheDocument();
    });

    mswTest("redirects to /wrapped for invalid UUID", async () => {
        await renderAppRoute(`/wrapped/not-a-valid-uuid?year=${year.toString()}`);

        await expect.poll(() => window.location.pathname).toBe("/wrapped");
    });

    mswTest("renders stars gained stat card", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect
            .element(screen.getByRole("heading", { name: "Stars Gained" }).first())
            .toBeInTheDocument();
    });

    mswTest("search navigates to different player's wrapped", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        const searchInput = screen.getByRole("combobox", {
            name: "Search players",
        });
        await expect.element(searchInput).toBeInTheDocument();

        await searchInput.fill(USERS.player2.username);
        await userEvent.keyboard("{Enter}");

        await expect
            .poll(() => window.location.pathname)
            .toBe(`/wrapped/${USERS.player2.uuid}`);
    });

    mswTest("records player visit in localStorage on load", async () => {
        await renderAppRoute(wrappedUrl);

        await expect
            .poll(() => {
                const stored = localStorage.getItem("playerVisits");
                return stored?.includes(USERS.player1.uuid) ?? false;
            })
            .toBe(true);
    });

    mswTest("renders session length stats", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect
            .element(screen.getByText("Longest Session").first())
            .toBeInTheDocument();
    });

    mswTest("contains meta description with player name", async () => {
        await renderAppRoute(wrappedUrl);

        await expect
            .poll(() => {
                const meta = document.querySelector('meta[name="description"]');
                return (
                    meta?.getAttribute("content")?.includes(USERS.player1.username) ??
                    false
                );
            })
            .toBe(true);
    });

    mswTest("contains canonical link", async () => {
        await renderAppRoute(wrappedUrl);

        await expect
            .poll(() => {
                const link = document.querySelector('link[rel="canonical"]');
                return link?.getAttribute("href");
            })
            .toBe(`https://prismoverlay.com/wrapped/${USERS.player1.uuid}`);
    });

    mswTest(
        "no yearStats shows download prompt",
        async ({ worker }: { worker: import("msw/browser").SetupWorker }) => {
            worker.use(
                http.get(
                    "http://localhost:5173/flashlight/v1/wrapped/:uuid/:year",
                    () => {
                        return HttpResponse.json({
                            success: true,
                            uuid: USERS.player1.uuid,
                            year,
                            totalSessions: 0,
                            nonConsecutiveSessions: 0,
                            yearStats: null,
                            sessionStats: null,
                        });
                    },
                ),
            );

            await renderAppRoute(wrappedUrl);

            await expect
                .poll(() => {
                    return document.body.textContent.includes(
                        "didn't record any stats",
                    );
                })
                .toBe(true);
        },
    );

    mswTest(
        "zero sessions shows NoSessionsAlert with year stats",
        async ({ worker }: { worker: import("msw/browser").SetupWorker }) => {
            worker.use(
                http.get(
                    "http://localhost:5173/flashlight/v1/wrapped/:uuid/:year",
                    (req) => {
                        const uuid = req.params.uuid as string;
                        const yearParam = parseInt(req.params.year as string, 10);
                        const startTime = `${yearParam.toString()}-01-01T00:00:00.000Z`;
                        const endTime = `${yearParam.toString()}-12-31T23:59:59.999Z`;

                        return HttpResponse.json({
                            success: true,
                            uuid,
                            year: yearParam,
                            totalSessions: 0,
                            nonConsecutiveSessions: 0,
                            yearStats: {
                                start: {
                                    uuid,
                                    queriedAt: startTime,
                                    experience: 500000,
                                    solo: {
                                        winstreak: 3,
                                        gamesPlayed: 100,
                                        wins: 60,
                                        losses: 40,
                                        bedsBroken: 80,
                                        bedsLost: 30,
                                        finalKills: 150,
                                        finalDeaths: 50,
                                        kills: 200,
                                        deaths: 100,
                                    },
                                    doubles: {
                                        winstreak: 3,
                                        gamesPlayed: 100,
                                        wins: 60,
                                        losses: 40,
                                        bedsBroken: 80,
                                        bedsLost: 30,
                                        finalKills: 150,
                                        finalDeaths: 50,
                                        kills: 200,
                                        deaths: 100,
                                    },
                                    threes: {
                                        winstreak: 3,
                                        gamesPlayed: 100,
                                        wins: 60,
                                        losses: 40,
                                        bedsBroken: 80,
                                        bedsLost: 30,
                                        finalKills: 150,
                                        finalDeaths: 50,
                                        kills: 200,
                                        deaths: 100,
                                    },
                                    fours: {
                                        winstreak: 3,
                                        gamesPlayed: 100,
                                        wins: 60,
                                        losses: 40,
                                        bedsBroken: 80,
                                        bedsLost: 30,
                                        finalKills: 150,
                                        finalDeaths: 50,
                                        kills: 200,
                                        deaths: 100,
                                    },
                                    overall: {
                                        winstreak: 12,
                                        gamesPlayed: 400,
                                        wins: 240,
                                        losses: 160,
                                        bedsBroken: 320,
                                        bedsLost: 120,
                                        finalKills: 600,
                                        finalDeaths: 200,
                                        kills: 800,
                                        deaths: 400,
                                    },
                                },
                                end: {
                                    uuid,
                                    queriedAt: endTime,
                                    experience: 1500000,
                                    solo: {
                                        winstreak: 9,
                                        gamesPlayed: 300,
                                        wins: 180,
                                        losses: 120,
                                        bedsBroken: 240,
                                        bedsLost: 90,
                                        finalKills: 450,
                                        finalDeaths: 150,
                                        kills: 600,
                                        deaths: 300,
                                    },
                                    doubles: {
                                        winstreak: 9,
                                        gamesPlayed: 300,
                                        wins: 180,
                                        losses: 120,
                                        bedsBroken: 240,
                                        bedsLost: 90,
                                        finalKills: 450,
                                        finalDeaths: 150,
                                        kills: 600,
                                        deaths: 300,
                                    },
                                    threes: {
                                        winstreak: 9,
                                        gamesPlayed: 300,
                                        wins: 180,
                                        losses: 120,
                                        bedsBroken: 240,
                                        bedsLost: 90,
                                        finalKills: 450,
                                        finalDeaths: 150,
                                        kills: 600,
                                        deaths: 300,
                                    },
                                    fours: {
                                        winstreak: 9,
                                        gamesPlayed: 300,
                                        wins: 180,
                                        losses: 120,
                                        bedsBroken: 240,
                                        bedsLost: 90,
                                        finalKills: 450,
                                        finalDeaths: 150,
                                        kills: 600,
                                        deaths: 300,
                                    },
                                    overall: {
                                        winstreak: 36,
                                        gamesPlayed: 1200,
                                        wins: 720,
                                        losses: 480,
                                        bedsBroken: 960,
                                        bedsLost: 360,
                                        finalKills: 1800,
                                        finalDeaths: 600,
                                        kills: 2400,
                                        deaths: 1200,
                                    },
                                },
                            },
                            sessionStats: null,
                        });
                    },
                ),
            );

            await renderAppRoute(wrappedUrl);

            // Should show the no-sessions alert with download link
            await expect
                .poll(() => {
                    return document.body.textContent.includes(
                        "didn't record any sessions",
                    );
                })
                .toBe(true);

            // Should still show year stats cards
            await expect
                .poll(() => {
                    return document.body.textContent.includes("Games Played");
                })
                .toBe(true);
        },
    );

    mswTest(
        "low session coverage shows warning alert",
        async ({ worker }: { worker: import("msw/browser").SetupWorker }) => {
            worker.use(
                http.get(
                    "http://localhost:5173/flashlight/v1/wrapped/:uuid/:year",
                    (req) => {
                        const uuid = req.params.uuid as string;
                        const yearParam = parseInt(req.params.year as string, 10);
                        const response = makeWrappedResponse(uuid, yearParam);
                        // Set coverage to below 50%
                        response.sessionStats.sessionCoverage.gamesPlayedPercentage = 0.2;
                        return HttpResponse.json(response);
                    },
                ),
            );

            await renderAppRoute(wrappedUrl);

            await expect
                .poll(() => {
                    return document.body.textContent.includes(
                        "Session coverage is low",
                    );
                })
                .toBe(true);
        },
    );

    mswTest("non-normalized UUID redirects to normalized version", async () => {
        const undashed = USERS.player1.uuid.replaceAll("-", "");
        await renderAppRoute(`/wrapped/${undashed}?year=${year.toString()}`);

        await expect
            .poll(() => window.location.pathname)
            .toBe(`/wrapped/${USERS.player1.uuid}`);
    });

    mswTest("renders average session length stat", async () => {
        const { screen } = await renderAppRoute(wrappedUrl);

        await expect
            .element(screen.getByText("Avg Length").first())
            .toBeInTheDocument();
    });
});
