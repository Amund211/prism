import { describe, expect } from "vitest";
import { mswTest } from "#test/msw-test.ts";
import { renderAppRoute } from "#test/render.tsx";

describe("About page", () => {
    mswTest("renders Discord section", async () => {
        const { screen } = await renderAppRoute("/about");

        await expect
            .element(screen.getByRole("heading", { name: "Discord" }))
            .toBeInTheDocument();

        await expect
            .element(
                screen.getByRole("link", {
                    name: "Join our Discord server",
                }),
            )
            .toBeInTheDocument();
    });

    mswTest("renders Thanks section with Mineatar credit", async () => {
        const { screen } = await renderAppRoute("/about");

        await expect.element(screen.getByText("Thanks")).toBeInTheDocument();

        await expect.element(screen.getByText("Mineatar")).toBeInTheDocument();
    });

    mswTest("renders Disclaimer section", async () => {
        const { screen } = await renderAppRoute("/about");

        await expect.element(screen.getByText("Disclaimer")).toBeInTheDocument();
    });

    mswTest("renders Hypixel API Policy section", async () => {
        const { screen } = await renderAppRoute("/about");

        await expect
            .element(screen.getByRole("heading", { name: "Hypixel API Policy" }))
            .toBeInTheDocument();
    });

    mswTest("renders Privacy section", async () => {
        const { screen } = await renderAppRoute("/about");

        await expect.element(screen.getByText("Privacy")).toBeInTheDocument();
    });

    mswTest("Discord link has correct href and opens in new tab", async () => {
        const { screen } = await renderAppRoute("/about");

        const link = screen.getByRole("link", {
            name: "Join our Discord server",
        });
        await expect.element(link).toBeInTheDocument();
        await expect
            .element(link)
            .toHaveAttribute("href", "https://discord.gg/k4FGUnEHYg");
        await expect.element(link).toHaveAttribute("target", "_blank");
    });

    mswTest("Mineatar link has correct href", async () => {
        const { screen } = await renderAppRoute("/about");

        const link = screen.getByRole("link", { name: "Mineatar" });
        await expect.element(link).toBeInTheDocument();
        await expect.element(link).toHaveAttribute("href", "https://mineatar.io/");
    });

    mswTest("contains meta description", async () => {
        await renderAppRoute("/about");

        await expect
            .poll(() => {
                return document.querySelector('meta[content*="Prism Overlay"]');
            })
            .toBeInTheDocument();
    });

    mswTest("contains canonical link", async () => {
        await renderAppRoute("/about");

        await expect
            .poll(() => {
                return document.querySelector(
                    'link[href="https://prismoverlay.com/about"]',
                );
            })
            .toBeInTheDocument();
    });

    mswTest(
        "Hypixel API policy link has correct href and opens in new tab",
        async () => {
            const { screen } = await renderAppRoute("/about");

            const link = screen.getByRole("link", {
                name: "Hypixel API policy",
            });
            await expect.element(link).toBeInTheDocument();
            await expect
                .element(link)
                .toHaveAttribute("href", "https://developer.hypixel.net/policies/");
            await expect.element(link).toHaveAttribute("target", "_blank");
        },
    );

    mswTest("Privacy section Discord link has correct href", async () => {
        await renderAppRoute("/about");

        // There are two Discord links on the page - the Privacy section one is the second
        await expect
            .poll(() => {
                const links = document.querySelectorAll(
                    'a[href="https://discord.gg/k4FGUnEHYg"]',
                );
                return links.length;
            })
            .toBeGreaterThanOrEqual(2);
    });
});
