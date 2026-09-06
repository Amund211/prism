import { describe, expect } from "vitest";

import { mswTest } from "#test/msw-test.ts";
import { renderAppRoute } from "#test/render.tsx";

describe("Privacy page", () => {
    mswTest("renders the heading and the last updated date", async () => {
        const { screen } = await renderAppRoute("/privacy");

        await expect
            .element(screen.getByRole("heading", { name: "Privacy policy", level: 1 }))
            .toBeInTheDocument();

        await expect.element(screen.getByText(/^Last updated /)).toBeInTheDocument();
    });

    mswTest("renders every section heading", async () => {
        const { screen } = await renderAppRoute("/privacy");

        const names = [
            "Scope",
            "What we handle",
            "Why we handle it",
            "What stays on your computer",
            "What we do not do",
            "Third parties",
            "How long we keep it",
            "Your rights",
            "Children",
            "Changes",
            "Contact",
        ];

        await Promise.all(
            names.map(async (name) => {
                await expect
                    .element(screen.getByRole("heading", { name, level: 2 }))
                    .toBeInTheDocument();
            }),
        );
    });

    mswTest("names the third parties it shares data with", async () => {
        const { screen } = await renderAppRoute("/privacy");

        const names = ["Hypixel API", "Mojang API", "Urchin", "Sentry", "Google Cloud"];

        await Promise.all(
            names.map(async (name) => {
                await expect
                    .element(screen.getByText(name, { exact: true }).first())
                    .toBeInTheDocument();
            }),
        );
    });

    mswTest("links to the terms of service", async () => {
        const { screen } = await renderAppRoute("/privacy");

        const link = screen.getByRole("link", { name: "terms of service" });
        await expect.element(link).toBeInTheDocument();
        await expect.element(link).toHaveAttribute("href", "/terms");
    });

    mswTest("contains meta description and canonical link", async () => {
        await renderAppRoute("/privacy");

        await expect
            .poll(() => {
                return document.querySelector(
                    'link[href="https://prismoverlay.com/privacy"]',
                );
            })
            .toBeInTheDocument();

        await expect
            .poll(() => {
                return document.querySelector('meta[name="description"]');
            })
            .toBeInTheDocument();
    });
});
