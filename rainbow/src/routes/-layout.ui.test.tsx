import { describe, expect } from "vitest";
import { page } from "vitest/browser";

import { getWrappedYear } from "#helpers/wrapped.ts";
import { USERS } from "#mocks/data.ts";
import { mswTest } from "#test/msw-test.ts";
import { renderAppRoute } from "#test/render.tsx";

describe("Layout - Desktop navigation", () => {
    mswTest("renders all route links in sidebar", async () => {
        await page.viewport(1280, 720);
        const { screen } = await renderAppRoute("/");

        await expect.element(screen.getByText("Session stats")).toBeInTheDocument();
        await expect.element(screen.getByText("History explorer")).toBeInTheDocument();
        await expect
            .element(screen.getByText(`Wrapped ${getWrappedYear().toString()}`).first())
            .toBeInTheDocument();
        await expect.element(screen.getByText("Downloads").first()).toBeInTheDocument();
        await expect.element(screen.getByText("Settings").first()).toBeInTheDocument();
        await expect.element(screen.getByText("About").first()).toBeInTheDocument();
    });

    mswTest("clicking Session stats navigates", async () => {
        await page.viewport(1280, 720);
        const { screen } = await renderAppRoute("/");

        await screen.getByText("Session stats").click();

        await expect.poll(() => globalThis.location.pathname).toMatch(/^\/session/);
    });

    mswTest("clicking History explorer navigates", async () => {
        await page.viewport(1280, 720);
        const { screen } = await renderAppRoute("/");

        await screen.getByText("History explorer").click();

        await expect.poll(() => globalThis.location.pathname).toBe("/history/explore");
    });

    mswTest("clicking Wrapped navigates", async () => {
        await page.viewport(1280, 720);
        const { screen } = await renderAppRoute("/");

        await screen
            .getByText(`Wrapped ${getWrappedYear().toString()}`)
            .first()
            .click();

        await expect.poll(() => globalThis.location.pathname).toMatch(/^\/wrapped/);
    });

    mswTest("clicking Downloads navigates", async () => {
        await page.viewport(1280, 720);
        const { screen } = await renderAppRoute("/");

        await screen.getByText("Downloads").first().click();

        await expect.poll(() => globalThis.location.pathname).toBe("/downloads");
    });

    mswTest("clicking Settings navigates", async () => {
        await page.viewport(1280, 720);
        const { screen } = await renderAppRoute("/");

        await screen.getByText("Settings").first().click();

        await expect.poll(() => globalThis.location.pathname).toBe("/settings");
    });

    mswTest("clicking About navigates", async () => {
        await page.viewport(1280, 720);
        const { screen } = await renderAppRoute("/");

        await screen.getByText("About").first().click();

        await expect.poll(() => globalThis.location.pathname).toBe("/about");
    });

    mswTest("logo navigates home", async () => {
        await page.viewport(1280, 720);
        await renderAppRoute("/about");

        // The drawer logo is the visible one at desktop width
        // Click the logo image in the drawer (second instance since mobile AppBar has first)
        await expect
            .poll(() => {
                const logos = document.querySelectorAll(
                    'img[alt="Prism Overlay logo"]',
                );
                for (const logo of logos) {
                    const link = logo.closest("a");
                    if (link && link.offsetParent !== null) {
                        link.click();
                        return true;
                    }
                }
                return false;
            })
            .toBe(true);

        await expect.poll(() => globalThis.location.pathname).toBe("/");
    });

    mswTest("active route is highlighted", async () => {
        await page.viewport(1280, 720);
        await renderAppRoute("/about");

        await expect
            .poll(() => {
                // TanStack Router sets data-status="active" or aria-current on active links
                const aboutLinks = document.querySelectorAll(
                    '[data-status="active"], [aria-current="page"]',
                );
                return [...aboutLinks].some((el) => el.textContent.includes("About"));
            })
            .toBe(true);
    });
});

describe("Layout - Mobile navigation", () => {
    const openBurgerMenu = async (
        screen: Awaited<ReturnType<typeof renderAppRoute>>["screen"],
    ) => {
        const menuButton = screen.getByLabelText("Open toolbar menu");
        await expect.element(menuButton).toBeInTheDocument();
        await menuButton.click();
    };

    mswTest("burger menu button renders", async () => {
        await page.viewport(375, 667);
        const { screen } = await renderAppRoute("/");

        await expect
            .element(screen.getByLabelText("Open toolbar menu"))
            .toBeInTheDocument();
    });

    mswTest("burger menu shows all links", async () => {
        await page.viewport(375, 667);
        const { screen } = await renderAppRoute("/");

        await openBurgerMenu(screen);

        await expect
            .element(screen.getByRole("menuitem", { name: "Session stats" }))
            .toBeInTheDocument();
        await expect
            .element(screen.getByRole("menuitem", { name: "History explorer" }))
            .toBeInTheDocument();
        await expect
            .element(
                screen.getByRole("menuitem", {
                    name: `Wrapped ${getWrappedYear().toString()}`,
                }),
            )
            .toBeInTheDocument();
        await expect
            .element(screen.getByRole("menuitem", { name: "Downloads" }))
            .toBeInTheDocument();
        await expect
            .element(screen.getByRole("menuitem", { name: "Settings" }))
            .toBeInTheDocument();
        await expect
            .element(screen.getByRole("menuitem", { name: "About" }))
            .toBeInTheDocument();
    });

    mswTest("clicking Session stats navigates", async () => {
        await page.viewport(375, 667);
        const { screen } = await renderAppRoute("/");

        await openBurgerMenu(screen);
        await screen.getByRole("menuitem", { name: "Session stats" }).click();

        await expect.poll(() => globalThis.location.pathname).toMatch(/^\/session/);
    });

    mswTest("clicking History explorer navigates", async () => {
        await page.viewport(375, 667);
        const { screen } = await renderAppRoute("/");

        await openBurgerMenu(screen);
        await screen.getByRole("menuitem", { name: "History explorer" }).click();

        await expect.poll(() => globalThis.location.pathname).toBe("/history/explore");
    });

    mswTest("clicking Wrapped navigates", async () => {
        await page.viewport(375, 667);
        const { screen } = await renderAppRoute("/");

        await openBurgerMenu(screen);
        await screen
            .getByRole("menuitem", {
                name: `Wrapped ${getWrappedYear().toString()}`,
            })
            .click();

        await expect.poll(() => globalThis.location.pathname).toMatch(/^\/wrapped/);
    });

    mswTest("clicking Downloads navigates", async () => {
        await page.viewport(375, 667);
        const { screen } = await renderAppRoute("/");

        await openBurgerMenu(screen);
        await screen.getByRole("menuitem", { name: "Downloads" }).click();

        await expect.poll(() => globalThis.location.pathname).toBe("/downloads");
    });

    mswTest("clicking Settings navigates", async () => {
        await page.viewport(375, 667);
        const { screen } = await renderAppRoute("/");

        await openBurgerMenu(screen);
        await screen.getByRole("menuitem", { name: "Settings" }).click();

        await expect.poll(() => globalThis.location.pathname).toBe("/settings");
    });

    mswTest("clicking About navigates", async () => {
        await page.viewport(375, 667);
        const { screen } = await renderAppRoute("/");

        await openBurgerMenu(screen);
        await screen.getByRole("menuitem", { name: "About" }).click();

        await expect.poll(() => globalThis.location.pathname).toBe("/about");
    });

    mswTest("logo navigates home", async () => {
        await page.viewport(375, 667);
        await renderAppRoute("/about");

        // Click the visible AppBar logo
        await expect
            .poll(() => {
                const logos = document.querySelectorAll(
                    'img[alt="Prism Overlay logo"]',
                );
                for (const logo of logos) {
                    const link = logo.closest("a");
                    if (link && link.offsetParent !== null) {
                        link.click();
                        return true;
                    }
                }
                return false;
            })
            .toBe(true);

        await expect.poll(() => globalThis.location.pathname).toBe("/");
    });

    mswTest("menu closes after clicking a link", async () => {
        await page.viewport(375, 667);
        const { screen } = await renderAppRoute("/");

        await openBurgerMenu(screen);

        // Verify menu is open
        await expect
            .element(screen.getByRole("menuitem", { name: "About" }))
            .toBeInTheDocument();

        // Click a nav link
        await screen.getByRole("menuitem", { name: "About" }).click();

        // Menu items should no longer be visible
        await expect
            .element(screen.getByRole("menuitem", { name: "About" }))
            .not.toBeInTheDocument();
    });
});

describe("Layout - active route highlighting updates on navigation", () => {
    mswTest("active link changes when navigating to a different route", async () => {
        await page.viewport(1280, 720);
        const { screen } = await renderAppRoute("/about");

        // About should be highlighted initially
        await expect
            .poll(() => {
                const activeLinks = document.querySelectorAll(
                    '[data-status="active"], [aria-current="page"]',
                );
                return [...activeLinks].some((el) => el.textContent.includes("About"));
            })
            .toBe(true);

        // Navigate to Downloads
        await screen.getByText("Downloads").first().click();

        await expect.poll(() => globalThis.location.pathname).toBe("/downloads");

        // Downloads should now be highlighted, About should not be
        await expect
            .poll(() => {
                const activeLinks = document.querySelectorAll(
                    '[data-status="active"], [aria-current="page"]',
                );
                return [...activeLinks].some((el) =>
                    el.textContent.includes("Downloads"),
                );
            })
            .toBe(true);
    });
});

describe("Layout - sidebar navigation links include current user", () => {
    mswTest("session stats link includes currentUser UUID when set", async () => {
        await page.viewport(1280, 720);
        localStorage.setItem("currentUser", USERS.player1.uuid);
        await renderAppRoute("/about");

        // The Session stats link in the sidebar should include the currentUser's UUID
        await expect
            .poll(() => {
                const links = document.querySelectorAll(
                    `a[href*="${USERS.player1.uuid}"]`,
                );
                return [...links].some((link) =>
                    link.textContent.includes("Session stats"),
                );
            })
            .toBe(true);
    });

    mswTest("wrapped link includes currentUser UUID when set", async () => {
        await page.viewport(1280, 720);
        localStorage.setItem("currentUser", USERS.player1.uuid);
        await renderAppRoute("/about");

        await expect
            .poll(() => {
                const links = document.querySelectorAll(
                    `a[href*="${USERS.player1.uuid}"]`,
                );
                return [...links].some((link) => link.textContent.includes("Wrapped"));
            })
            .toBe(true);
    });

    mswTest("history explorer link includes currentUser UUID when set", async () => {
        await page.viewport(1280, 720);
        localStorage.setItem("currentUser", USERS.player1.uuid);
        await renderAppRoute("/about");

        await expect
            .poll(() => {
                const links = document.querySelectorAll(
                    `a[href*="${USERS.player1.uuid}"]`,
                );
                return [...links].some((link) =>
                    link.textContent.includes("History explorer"),
                );
            })
            .toBe(true);
    });
});

describe("Layout - mobile navigation links include current user", () => {
    mswTest("session stats mobile menu link includes currentUser UUID", async () => {
        await page.viewport(375, 667);
        localStorage.setItem("currentUser", USERS.player1.uuid);
        const { screen } = await renderAppRoute("/about");

        const menuButton = screen.getByLabelText("Open toolbar menu");
        await expect.element(menuButton).toBeInTheDocument();
        await menuButton.click();

        await expect
            .poll(() => {
                const menuItems = document.querySelectorAll('[role="menuitem"]');
                return [...menuItems].some(
                    (item) =>
                        item.textContent.includes("Session stats") &&
                        item.getAttribute("href")?.includes(USERS.player1.uuid) ===
                            true,
                );
            })
            .toBe(true);
    });
});

describe("Layout - dark mode", () => {
    mswTest("dark mode switch renders in desktop layout", async () => {
        await page.viewport(1280, 720);
        await renderAppRoute("/");

        // Look for the dark mode toggle buttons (light/system/dark)
        await expect
            .poll(() => {
                const toggleGroup = document.querySelector(
                    ".MuiToggleButtonGroup-root",
                );
                return toggleGroup !== null;
            })
            .toBe(true);
    });

    mswTest("dark mode switch renders in mobile layout", async () => {
        await page.viewport(375, 667);
        await renderAppRoute("/");

        await expect
            .poll(() => {
                const toggleGroup = document.querySelector(
                    ".MuiToggleButtonGroup-root",
                );
                return toggleGroup !== null;
            })
            .toBe(true);
    });

    mswTest("dark mode toggle persists selection to localStorage", async () => {
        await page.viewport(1280, 720);
        const { screen } = await renderAppRoute("/");

        const group = screen.getByRole("group", {
            name: "Color theme switcher",
        });
        await expect.element(group).toBeInTheDocument();

        // Click "Dark mode" toggle button
        await expect
            .poll(() => {
                const darkBtn = document.querySelector(
                    '[aria-label="Color theme switcher"] [value="dark"]',
                );
                if (darkBtn) {
                    (darkBtn as HTMLElement).click();
                    return true;
                }
                return false;
            })
            .toBe(true);

        // MUI stores the mode in localStorage under mui-mode
        await expect
            .poll(() => {
                return localStorage.getItem("mui-mode");
            })
            .toBe("dark");
    });
});
