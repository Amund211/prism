import { describe, expect } from "vitest";
import { USERS } from "#mocks/data.ts";
import { mswTest } from "#test/msw-test.ts";
import { renderAppRoute } from "#test/render.tsx";
import { userEvent } from "vitest/browser";

describe("Settings page", () => {
    mswTest("renders default player heading", async () => {
        const { screen } = await renderAppRoute("/settings");

        await expect.element(screen.getByText("Default player")).toBeInTheDocument();
    });

    mswTest("renders player search input", async () => {
        const { screen } = await renderAppRoute("/settings");

        await expect
            .element(screen.getByPlaceholder("Set default player"))
            .toBeInTheDocument();
    });

    mswTest("setting a default player updates localStorage", async () => {
        const { screen } = await renderAppRoute("/settings");

        const input = screen.getByPlaceholder("Set default player");
        await expect.element(input).toBeInTheDocument();

        await input.fill(USERS.player1.username);
        await userEvent.keyboard("{Enter}");

        await expect
            .poll(() => localStorage.getItem("currentUser"))
            .toBe(USERS.player1.uuid);
    });

    mswTest("clearing default player updates localStorage to null", async () => {
        // Pre-set a default player
        localStorage.setItem("currentUser", USERS.player1.uuid);

        await renderAppRoute("/settings");

        // Wait for the player chip to appear
        await expect
            .poll(() => {
                const chips = document.querySelectorAll(".MuiChip-root");
                return [...chips].some((c) => c.textContent === USERS.player1.username);
            })
            .toBe(true);

        // Click the chip's delete button to remove the player
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

        // localStorage should be updated to null
        await expect.poll(() => localStorage.getItem("currentUser")).toBeNull();
    });

    mswTest(
        "replacing default player with different player updates localStorage",
        async () => {
            localStorage.setItem("currentUser", USERS.player1.uuid);

            const { screen } = await renderAppRoute("/settings");

            // Wait for the player1 chip to appear
            await expect
                .poll(() => {
                    const chips = document.querySelectorAll(".MuiChip-root");
                    return [...chips].some(
                        (c) => c.textContent === USERS.player1.username,
                    );
                })
                .toBe(true);

            // Add player2 via the input
            const input = screen.getByPlaceholder("Set default player");
            await input.fill(USERS.player2.username);
            await userEvent.keyboard("{Enter}");

            // localStorage should now have player2's UUID
            await expect
                .poll(() => localStorage.getItem("currentUser"))
                .toBe(USERS.player2.uuid);
        },
    );

    mswTest("renders info tooltip icon", async () => {
        const { screen } = await renderAppRoute("/settings");

        await expect
            .element(screen.getByTestId("InfoOutlinedIcon"))
            .toBeInTheDocument();
    });

    mswTest("contains meta description", async () => {
        await renderAppRoute("/settings");

        await expect
            .poll(() => {
                return document.querySelector('meta[content*="Change your settings"]');
            })
            .toBeInTheDocument();
    });

    mswTest("contains canonical link", async () => {
        await renderAppRoute("/settings");

        await expect
            .poll(() => {
                return document.querySelector(
                    'link[href="https://prismoverlay.com/settings"]',
                );
            })
            .toBeInTheDocument();
    });

    mswTest("pre-set default player shows chip on load", async () => {
        localStorage.setItem("currentUser", USERS.player1.uuid);

        await renderAppRoute("/settings");

        await expect
            .poll(() => {
                const chips = document.querySelectorAll(".MuiChip-root");
                return [...chips].some((c) => c.textContent === USERS.player1.username);
            })
            .toBe(true);
    });

    mswTest("navigating away and back preserves default player", async () => {
        localStorage.setItem("currentUser", USERS.player1.uuid);

        await renderAppRoute("/settings");

        // Confirm the chip renders initially
        await expect
            .poll(() => {
                const chips = document.querySelectorAll(".MuiChip-root");
                return [...chips].some((c) => c.textContent === USERS.player1.username);
            })
            .toBe(true);

        // Navigate away to about page
        await expect
            .poll(() => {
                const aboutLink = document.querySelector('a[href="/about"]');
                if (aboutLink) {
                    (aboutLink as HTMLElement).click();
                    return true;
                }
                return false;
            })
            .toBe(true);

        await expect.poll(() => globalThis.location.pathname).toBe("/about");

        // Navigate back to settings
        await expect
            .poll(() => {
                const settingsLink = document.querySelector('a[href="/settings"]');
                if (settingsLink) {
                    (settingsLink as HTMLElement).click();
                    return true;
                }
                return false;
            })
            .toBe(true);

        await expect.poll(() => globalThis.location.pathname).toBe("/settings");

        // Player should still be set
        await expect
            .poll(() => {
                const chips = document.querySelectorAll(".MuiChip-root");
                return [...chips].some((c) => c.textContent === USERS.player1.username);
            })
            .toBe(true);
    });
});
