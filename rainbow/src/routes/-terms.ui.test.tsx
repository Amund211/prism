import { describe, expect } from "vitest";

import { mswTest } from "#test/msw-test.ts";
import { renderAppRoute } from "#test/render.tsx";

describe("Terms page", () => {
    mswTest("renders the heading and the last updated date", async () => {
        const { screen } = await renderAppRoute("/terms");

        await expect
            .element(
                screen.getByRole("heading", { name: "Terms of service", level: 1 }),
            )
            .toBeInTheDocument();

        await expect.element(screen.getByText(/^Last updated /)).toBeInTheDocument();
    });

    mswTest("renders every section heading", async () => {
        const { screen } = await renderAppRoute("/terms");

        const names = [
            "Scope",
            "No affiliation",
            "Free service, no guarantees",
            "Acceptable use",
            "Other services",
            "Accounts",
            "No warranty",
            "Limitation of liability",
            "Source code",
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

    mswTest("disclaims affiliation with Mojang, Microsoft and Hypixel", async () => {
        const { screen } = await renderAppRoute("/terms");

        await expect
            .element(
                screen.getByText(
                    /not associated with, endorsed by or sponsored by Mojang Studios, Microsoft or The Hypixel Network/,
                ),
            )
            .toBeInTheDocument();
    });

    mswTest("links to the privacy policy", async () => {
        const { screen } = await renderAppRoute("/terms");

        const link = screen.getByRole("link", { name: "privacy policy" });
        await expect.element(link).toBeInTheDocument();
        await expect.element(link).toHaveAttribute("href", "/privacy");
    });

    mswTest("contains meta description and canonical link", async () => {
        await renderAppRoute("/terms");

        await expect
            .poll(() => {
                return document.querySelector(
                    'link[href="https://prismoverlay.com/terms"]',
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
