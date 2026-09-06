import { ThemeProvider } from "@mui/material";
import { describe, expect, test } from "vitest";
import { render } from "vitest-browser-react";

import { DarkModeSwitch } from "#components/DarkModeSwitch.tsx";
import { theme } from "#theme/index.ts";

// The OS preference is pinned to light (vitest.config.ts), so "system" resolves
// to light here. Labels are matched exactly: "Switch to dark mode" is a
// substring of "Switch to dark mode (system default)".
const EXACT = { exact: true };

const renderSwitch = async () => {
    const screen = await render(
        <ThemeProvider theme={theme} noSsr>
            <DarkModeSwitch />
        </ThemeProvider>,
    );
    return screen;
};

const storedMode = () => localStorage.getItem("mui-mode");

describe(DarkModeSwitch, () => {
    test("renders a single button", async () => {
        const screen = await renderSwitch();

        await expect.element(screen.getByRole("button")).toBeVisible();
        expect(document.querySelectorAll("button")).toHaveLength(1);
    });

    test("offers the opposite of the system default", async () => {
        const screen = await renderSwitch();

        await expect
            .element(screen.getByLabelText("Switch to dark mode", EXACT))
            .toBeVisible();
    });

    test("first press stores an explicit override", async () => {
        const screen = await renderSwitch();

        await screen.getByLabelText("Switch to dark mode", EXACT).click();

        await expect.poll(storedMode).toBe("dark");
    });

    test("second press returns to the system default", async () => {
        const screen = await renderSwitch();

        await screen.getByLabelText("Switch to dark mode", EXACT).click();
        await screen
            .getByLabelText("Switch to light mode (system default)", EXACT)
            .click();

        await expect.poll(storedMode).toBe("system");
    });

    test("keeps the override when the OS agrees with it", async () => {
        localStorage.setItem("mui-mode", "light");
        const screen = await renderSwitch();

        await expect
            .element(screen.getByLabelText("Switch to dark mode", EXACT))
            .toBeVisible();
        await screen.getByLabelText("Switch to dark mode", EXACT).click();

        await expect.poll(storedMode).toBe("dark");
    });
});
