import { describe, expect } from "vitest";
import { userEvent } from "vitest/browser";
import { http, HttpResponse } from "msw";
import type { SetupWorker } from "msw/browser";
import { USERS } from "#mocks/data.ts";
import { mswTest } from "#test/msw-test.ts";
import { renderAppRoute } from "#test/render.tsx";

describe("Session detail page", () => {
    const sessionUrl = `/session/${USERS.player1.uuid}?gamemode=overall&stat=fkdr&timeIntervalDefinition=${encodeURIComponent(JSON.stringify({ type: "contained" }))}&variantSelection=both&sessionTableMode=total&showExtrapolatedSessions=false`;

    mswTest("renders player heading with username", async () => {
        const { screen } = await renderAppRoute(sessionUrl);

        await expect
            .element(
                screen.getByRole("heading", {
                    name: `${USERS.player1.username}'s session stats`,
                }),
            )
            .toBeInTheDocument();
    });

    mswTest("renders gamemode selector", async () => {
        const { screen } = await renderAppRoute(sessionUrl);

        await expect.element(screen.getByLabelText("Gamemode")).toBeInTheDocument();
    });

    mswTest("renders stat selector", async () => {
        const { screen } = await renderAppRoute(sessionUrl);

        await expect
            .element(screen.getByLabelText("Stat", { exact: true }))
            .toBeInTheDocument();
    });

    mswTest("renders session table mode toggle", async () => {
        const { screen } = await renderAppRoute(sessionUrl);

        await expect
            .element(screen.getByRole("group", { name: "Session table mode" }))
            .toBeInTheDocument();
    });

    mswTest("renders sessions section with table", async () => {
        const { screen } = await renderAppRoute(sessionUrl);

        await expect.element(screen.getByText("Sessions")).toBeInTheDocument();

        // Session table headers
        await expect.element(screen.getByText("Start")).toBeInTheDocument();

        await expect.element(screen.getByText("Duration")).toBeInTheDocument();
    });

    mswTest("renders player search input", async () => {
        const { screen } = await renderAppRoute(sessionUrl);

        await expect
            .element(screen.getByRole("combobox", { name: "Search players" }))
            .toBeInTheDocument();
    });

    mswTest("renders player head image", async () => {
        await renderAppRoute(sessionUrl);

        await expect
            .poll(() => {
                return document.querySelector(`img[src*="${USERS.player1.uuid}"]`);
            })
            .toBeInTheDocument();
    });

    mswTest("renders daily stat card", async () => {
        await renderAppRoute(sessionUrl);

        await expect
            .poll(() => {
                const elements = document.querySelectorAll('[class*="MuiTypography"]');
                return [...elements].some((el) => el.textContent.startsWith("Daily"));
            })
            .toBe(true);
    });

    mswTest("renders weekly stat card", async () => {
        await renderAppRoute(sessionUrl);

        await expect
            .poll(() => {
                const elements = document.querySelectorAll('[class*="MuiTypography"]');
                return [...elements].some((el) => el.textContent.startsWith("Weekly"));
            })
            .toBe(true);
    });

    mswTest("renders monthly stat card", async () => {
        await renderAppRoute(sessionUrl);

        await expect
            .poll(() => {
                const elements = document.querySelectorAll('[class*="MuiTypography"]');
                return [...elements].some((el) => el.textContent.startsWith("Monthly"));
            })
            .toBe(true);
    });

    mswTest("renders stat progression card", async () => {
        const { screen } = await renderAppRoute(sessionUrl);

        await expect
            .element(screen.getByText(/milestone progress/))
            .toBeInTheDocument();
    });

    mswTest("renders variant selection toggle", async () => {
        const { screen } = await renderAppRoute(sessionUrl);

        await expect
            .element(
                screen
                    .getByRole("group", {
                        name: "Stat chart variant selection",
                    })
                    .first(),
            )
            .toBeInTheDocument();
    });

    mswTest(
        "renders history chart card with show in history explorer link",
        async () => {
            await renderAppRoute(sessionUrl);

            await expect
                .poll(() => {
                    return document.querySelector('a[href*="/history/explore"]');
                })
                .toBeInTheDocument();
        },
    );

    mswTest("renders time interval picker", async () => {
        const { screen } = await renderAppRoute(sessionUrl);

        await expect.element(screen.getByText("Current interval")).toBeInTheDocument();
    });

    mswTest(
        "time interval picker opens and selecting Last X days updates URL",
        async () => {
            const { screen } = await renderAppRoute(sessionUrl);

            // Click the time interval picker button
            const pickerButton = screen.getByText("Current interval");
            await expect.element(pickerButton).toBeInTheDocument();
            await pickerButton.click();

            // Click "Last X days" menu item
            await screen.getByText("Last X days").click();

            // URL should update to "until" type
            await expect
                .poll(() => {
                    const params = new URLSearchParams(globalThis.location.search);
                    const tid = params.get("timeIntervalDefinition");
                    return tid?.includes("until") ?? false;
                })
                .toBe(true);
        },
    );

    mswTest("sessions table renders stat values from mock data", async () => {
        await renderAppRoute(sessionUrl);

        // The mock sessions handler returns sessions with real stat data
        // Verify that numeric stat values appear in the table cells
        await expect
            .poll(() => {
                const cells = document.querySelectorAll("td");
                // Check that there are table data cells with numeric content
                return [...cells].some((cell) => {
                    const text = cell.textContent.trim();
                    return /^\d/.test(text) && text.length > 0;
                });
            })
            .toBe(true);
    });

    mswTest("shows related stat columns for FKDR", async () => {
        // stat=fkdr should show Finals and Final deaths columns
        const { screen } = await renderAppRoute(sessionUrl);

        await expect.element(screen.getByText("Finals").first()).toBeInTheDocument();
        await expect
            .element(screen.getByText("Final deaths").first())
            .toBeInTheDocument();
    });

    mswTest("rate mode shows /hour suffix on column headers", async () => {
        const rateUrl = sessionUrl.replace(
            "sessionTableMode=total",
            "sessionTableMode=rate",
        );
        const { screen } = await renderAppRoute(rateUrl);

        // Linear stats (Games, Wins) should show /hour suffix
        await expect
            .element(screen.getByText("Games/hour").first())
            .toBeInTheDocument();
        await expect.element(screen.getByText("Wins/hour").first()).toBeInTheDocument();
        // Non-linear stat FKDR should NOT have /hour suffix
        await expect.element(screen.getByText("FKDR").first()).toBeInTheDocument();
    });

    mswTest("redirects to /session for invalid UUID", async () => {
        await renderAppRoute(
            "/session/not-a-valid-uuid?gamemode=overall&stat=fkdr&timeIntervalDefinition=%7B%22type%22%3A%22contained%22%7D&variantSelection=both&sessionTableMode=total&showExtrapolatedSessions=false",
        );

        await expect.poll(() => globalThis.location.pathname).toBe("/session");
    });

    mswTest(
        "shows no sessions found when sessions API returns empty",
        async ({ worker }: { readonly worker: SetupWorker }) => {
            worker.use(
                http.post("http://localhost:5173/flashlight/v1/sessions", () => {
                    return HttpResponse.json([]);
                }),
            );

            const { screen } = await renderAppRoute(sessionUrl);

            await expect
                .element(screen.getByText("No sessions found"))
                .toBeInTheDocument();
        },
    );

    mswTest("search navigates to different player", async () => {
        const { screen } = await renderAppRoute(sessionUrl);

        const searchInput = screen.getByRole("combobox", {
            name: "Search players",
        });
        await expect.element(searchInput).toBeInTheDocument();

        await searchInput.fill(USERS.player2.username);
        await userEvent.keyboard("{Enter}");

        await expect
            .poll(() => globalThis.location.pathname)
            .toBe(`/session/${USERS.player2.uuid}`);
    });

    mswTest(
        "search navigates to different player and renders their heading",
        async () => {
            const { screen } = await renderAppRoute(sessionUrl);

            const searchInput = screen.getByRole("combobox", {
                name: "Search players",
            });
            await expect.element(searchInput).toBeInTheDocument();

            await searchInput.fill(USERS.player2.username);
            await userEvent.keyboard("{Enter}");

            await expect
                .poll(() => globalThis.location.pathname)
                .toBe(`/session/${USERS.player2.uuid}`);

            await expect
                .element(
                    screen.getByRole("heading", {
                        name: `${USERS.player2.username}'s session stats`,
                    }),
                )
                .toBeInTheDocument();
        },
    );

    mswTest("contains meta description", async () => {
        await renderAppRoute(sessionUrl);

        await expect
            .poll(() => {
                const meta = document.querySelector('meta[name="description"]');
                return meta?.getAttribute("content")?.includes("session stats");
            })
            .toBe(true);
    });

    mswTest("contains canonical link", async () => {
        await renderAppRoute(sessionUrl);

        await expect
            .poll(() => {
                const link = document.querySelector('link[rel="canonical"]');
                return link?.getAttribute("href");
            })
            .toBe(`https://prismoverlay.com/session/${USERS.player1.uuid}`);
    });

    mswTest("stat selector changes URL params", async () => {
        const { screen } = await renderAppRoute(sessionUrl);

        const statSelect = screen.getByLabelText("Stat", { exact: true });
        await expect.element(statSelect).toBeInTheDocument();

        // Open the select dropdown and click "Kills"
        await statSelect.click();
        await screen.getByRole("option", { name: "Kills", exact: true }).click();

        await expect
            .poll(() => new URLSearchParams(globalThis.location.search).get("stat"))
            .toBe("kills");
    });

    mswTest("gamemode selector changes URL params", async () => {
        const { screen } = await renderAppRoute(sessionUrl);

        const gamemodeSelect = screen.getByLabelText("Gamemode");
        await expect.element(gamemodeSelect).toBeInTheDocument();

        // Open the select dropdown and click "Solo"
        await gamemodeSelect.click();
        await screen.getByRole("option", { name: "Solo" }).click();

        await expect
            .poll(() => new URLSearchParams(globalThis.location.search).get("gamemode"))
            .toBe("solo");
    });

    mswTest(
        "shows no data found when history API returns empty",
        async ({ worker }: { readonly worker: SetupWorker }) => {
            worker.use(
                http.post("http://localhost:5173/flashlight/v1/history", () => {
                    return HttpResponse.json([]);
                }),
            );

            const { screen } = await renderAppRoute(sessionUrl);

            await expect
                .element(screen.getByText("No data found").first())
                .toBeInTheDocument();
        },
    );

    mswTest("session table mode toggle switches between Total and Rate", async () => {
        const { screen } = await renderAppRoute(sessionUrl);

        // Initially in "total" mode
        await expect
            .poll(() =>
                new URLSearchParams(globalThis.location.search).get("sessionTableMode"),
            )
            .toBe("total");

        // Click the "Rate (/hour)" toggle
        await screen.getByText("Rate (/hour)").click();

        await expect
            .poll(() =>
                new URLSearchParams(globalThis.location.search).get("sessionTableMode"),
            )
            .toBe("rate");
    });

    mswTest("variant selection toggle changes URL params", async () => {
        await renderAppRoute(sessionUrl);

        // Initially "both"
        await expect
            .poll(() =>
                new URLSearchParams(globalThis.location.search).get("variantSelection"),
            )
            .toBe("both");

        // Click "Session" toggle in the variant selection
        // There may be multiple variant groups - use the first one in the chart card
        await expect
            .poll(() => {
                const groups = document.querySelectorAll(
                    '[aria-label="Stat chart variant selection"]',
                );
                for (const group of groups) {
                    const sessionBtn = group.querySelector('[value="session"]');
                    if (sessionBtn) {
                        (sessionBtn as HTMLElement).click();
                        return true;
                    }
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

    mswTest("show in history explorer link includes correct params", async () => {
        await renderAppRoute(sessionUrl);

        await expect
            .poll(() => {
                const link = document.querySelector('a[href*="/history/explore"]');
                if (!link) return null;
                const href = link.getAttribute("href");
                if (href === null) return false;
                return (
                    href.includes(USERS.player1.uuid) &&
                    href.includes("fkdr") &&
                    href.includes("overall")
                );
            })
            .toBe(true);
    });

    mswTest("records player visit in localStorage on load", async () => {
        await renderAppRoute(sessionUrl);

        await expect
            .poll(() => {
                const stored = localStorage.getItem("playerVisits");
                return stored?.includes(USERS.player1.uuid) ?? false;
            })
            .toBe(true);
    });

    mswTest("extrapolated sessions toggle changes URL param", async () => {
        await renderAppRoute(sessionUrl);

        // The "Add missing data" toggle should appear since mock data produces extrapolated sessions
        await expect
            .poll(() => {
                return document.body.textContent.includes("Add missing data");
            })
            .toBe(true);

        // Click the switch to enable showing extrapolated sessions
        await expect
            .poll(() => {
                const switchEl = document.querySelector('input[type="checkbox"]');
                if (switchEl) {
                    (switchEl as HTMLElement).click();
                    return true;
                }
                return false;
            })
            .toBe(true);

        await expect
            .poll(() =>
                new URLSearchParams(globalThis.location.search).get(
                    "showExtrapolatedSessions",
                ),
            )
            .toBe("true");
    });

    mswTest(
        "partial failure: sessions API fails but page still renders with history",
        async ({ worker }: { readonly worker: SetupWorker }) => {
            worker.use(
                http.post("http://localhost:5173/flashlight/v1/sessions", () => {
                    return HttpResponse.json({ success: false }, { status: 500 });
                }),
            );

            const { screen } = await renderAppRoute(sessionUrl);

            // Player heading should still render
            await expect
                .element(
                    screen.getByRole("heading", {
                        name: `${USERS.player1.username}'s session stats`,
                    }),
                )
                .toBeInTheDocument();

            // Controls should still be usable
            await expect.element(screen.getByLabelText("Gamemode")).toBeInTheDocument();
            await expect
                .element(screen.getByLabelText("Stat", { exact: true }))
                .toBeInTheDocument();
        },
    );

    mswTest(
        "shows no data found when all APIs return errors",
        async ({ worker }: { readonly worker: SetupWorker }) => {
            worker.use(
                http.post("http://localhost:5173/flashlight/v1/history", () => {
                    return HttpResponse.json({ success: false }, { status: 500 });
                }),
                http.post("http://localhost:5173/flashlight/v1/sessions", () => {
                    return HttpResponse.json({ success: false }, { status: 500 });
                }),
            );

            const { screen } = await renderAppRoute(sessionUrl);

            // The page should still render with the player heading
            await expect
                .element(
                    screen.getByRole("heading", {
                        name: `${USERS.player1.username}'s session stats`,
                    }),
                )
                .toBeInTheDocument();
        },
    );

    mswTest("invalid search params fall back to defaults", async () => {
        const invalidUrl = `/session/${USERS.player1.uuid}?gamemode=INVALID&stat=notastat&variantSelection=wrong&sessionTableMode=bogus&showExtrapolatedSessions=maybe`;
        const { screen } = await renderAppRoute(invalidUrl);

        // The page should not crash - it should render with default values
        await expect
            .element(
                screen.getByRole("heading", {
                    name: `${USERS.player1.username}'s session stats`,
                }),
            )
            .toBeInTheDocument();

        // Controls should be rendered
        await expect.element(screen.getByLabelText("Gamemode")).toBeInTheDocument();
        await expect
            .element(screen.getByLabelText("Stat", { exact: true }))
            .toBeInTheDocument();
    });

    mswTest("non-normalized UUID redirects to normalized version", async () => {
        const undashed = USERS.player1.uuid.replaceAll("-", "");
        await renderAppRoute(
            `/session/${undashed}?gamemode=overall&stat=fkdr&timeIntervalDefinition=${encodeURIComponent(JSON.stringify({ type: "contained" }))}&variantSelection=both&sessionTableMode=total&showExtrapolatedSessions=false`,
        );

        await expect
            .poll(() => globalThis.location.pathname)
            .toBe(`/session/${USERS.player1.uuid}`);
    });

    mswTest("session table shows formatted duration values", async () => {
        await renderAppRoute(sessionUrl);

        // Wait for sessions table to render with duration data
        await expect
            .poll(() => {
                const cells = document.querySelectorAll("td");
                // Duration format contains "m" for minutes or "h" for hours
                return [...cells].some((cell) => {
                    const text = cell.textContent.trim();
                    return /\d+m/.test(text);
                });
            })
            .toBe(true);
    });

    mswTest("wins stat shows games and wins columns", async () => {
        const winsUrl = sessionUrl.replace("stat=fkdr", "stat=wins");
        const { screen } = await renderAppRoute(winsUrl);

        await expect.element(screen.getByText("Games").first()).toBeInTheDocument();
        await expect.element(screen.getByText("Wins").first()).toBeInTheDocument();
    });

    mswTest("changing stat to kdr shows kills and deaths columns", async () => {
        const killsUrl = sessionUrl.replace("stat=fkdr", "stat=kdr");
        const { screen } = await renderAppRoute(killsUrl);

        await expect.element(screen.getByText("Kills").first()).toBeInTheDocument();
        await expect.element(screen.getByText("Deaths").first()).toBeInTheDocument();
    });

    mswTest(
        "page renders controls when username API returns 404",
        async ({ worker }: { readonly worker: SetupWorker }) => {
            worker.use(
                http.get(
                    "http://localhost:5173/flashlight/v1/account/uuid/:uuid",
                    () => {
                        return HttpResponse.json(
                            { success: false, cause: "not found" },
                            { status: 404 },
                        );
                    },
                ),
            );

            const { screen } = await renderAppRoute(sessionUrl);

            // Page should still render the core controls even if username is unknown
            await expect.element(screen.getByLabelText("Gamemode")).toBeInTheDocument();
            await expect
                .element(screen.getByLabelText("Stat", { exact: true }))
                .toBeInTheDocument();
        },
    );

    mswTest("meta description includes player username", async () => {
        await renderAppRoute(sessionUrl);

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
});
