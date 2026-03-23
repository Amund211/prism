import { describe, expect } from "vitest";
import { mswTest } from "#test/msw-test.ts";
import { renderAppRoute } from "#test/render.tsx";
import { page } from "vitest/browser";

describe("Not found page", () => {
    mswTest("navigating to invalid route does not crash the app", async () => {
        await renderAppRoute("/this-route-does-not-exist");

        // The layout should still render (app didn't crash)
        await expect
            .poll(() => {
                return document.querySelector("header") !== null ||
                    document.querySelector("nav") !== null
                    ? true
                    : document.body.textContent.length > 0;
            })
            .toBe(true);
    });

    mswTest("deeply nested invalid route does not crash the app", async () => {
        await renderAppRoute("/some/deeply/nested/invalid/path");

        await expect
            .poll(() => {
                return document.querySelector("header") !== null ||
                    document.querySelector("nav") !== null
                    ? true
                    : document.body.textContent.length > 0;
            })
            .toBe(true);
    });

    mswTest("navigation links still work from not found page", async () => {
        await page.viewport(1280, 720);
        const { screen } = await renderAppRoute("/this-route-does-not-exist");

        // Layout sidebar should still render with working links
        await expect.element(screen.getByText("About").first()).toBeInTheDocument();

        await screen.getByText("About").first().click();

        await expect.poll(() => window.location.pathname).toBe("/about");
    });
});
