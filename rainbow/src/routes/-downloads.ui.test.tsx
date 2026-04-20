import { describe, expect } from "vitest";
import { mswTest } from "#test/msw-test.ts";
import { renderAppRoute } from "#test/render.tsx";

describe("Downloads page", () => {
    mswTest("renders archive table with download links", async () => {
        const { screen } = await renderAppRoute("/downloads");

        await expect
            .element(screen.getByRole("table", { name: "Archive" }))
            .toBeInTheDocument();

        // v1.11.0 appears 3 times (one per OS), check first one
        await expect
            .element(screen.getByText("Prism overlay v1.11.0").first())
            .toBeInTheDocument();
    });

    mswTest("renders version column headers", async () => {
        const { screen } = await renderAppRoute("/downloads");

        await expect.element(screen.getByText("Version")).toBeInTheDocument();

        await expect.element(screen.getByText("Operating System")).toBeInTheDocument();

        await expect.element(screen.getByText("Released At")).toBeInTheDocument();
    });

    mswTest("renders demo video", async () => {
        const { screen } = await renderAppRoute("/downloads");

        await expect
            .element(
                screen.getByRole("img", {
                    name: /Video of a bedwars game/,
                }),
            )
            .toBeInTheDocument();
    });

    mswTest("archive table contains download links pointing to GitHub", async () => {
        await renderAppRoute("/downloads");

        await expect
            .poll(() => {
                const links = document.querySelectorAll(
                    'a[href*="github.com/Amund211/prism/releases"]',
                );
                return links.length;
            })
            .toBeGreaterThan(0);
    });

    mswTest("all three OS types appear in the archive table", async () => {
        const { screen } = await renderAppRoute("/downloads");

        await expect.element(screen.getByText("Windows").first()).toBeInTheDocument();
        await expect.element(screen.getByText("Mac OS").first()).toBeInTheDocument();
        await expect.element(screen.getByText("Linux").first()).toBeInTheDocument();
    });

    mswTest("contains meta description", async () => {
        await renderAppRoute("/downloads");

        await expect
            .poll(() => {
                return document.querySelector(
                    'meta[content*="Download Prism Overlay"]',
                );
            })
            .toBeInTheDocument();
    });

    mswTest("contains canonical link", async () => {
        await renderAppRoute("/downloads");

        await expect
            .poll(() => {
                return document.querySelector(
                    'link[href="https://prismoverlay.com/downloads"]',
                );
            })
            .toBeInTheDocument();
    });

    mswTest("renders latest download section for detected OS", async () => {
        await renderAppRoute("/downloads");

        // In headless Chromium on Linux, the OS detection returns "Linux"
        // so the "Download for Linux" image should be visible
        await expect
            .poll(() => {
                const img = document.querySelector(
                    'img[alt="Download for Linux"], img[alt="Download for Windows"], img[alt="Download for Mac"]',
                );
                return img !== null;
            })
            .toBe(true);
    });

    mswTest("renders OS logo attributions", async () => {
        const { screen } = await renderAppRoute("/downloads");

        await expect
            .element(screen.getByText(/Windows and the Windows logo/))
            .toBeInTheDocument();

        await expect
            .element(screen.getByText(/macOS and the Apple logo/))
            .toBeInTheDocument();

        await expect
            .element(screen.getByText(/Linux is the registered trademark/))
            .toBeInTheDocument();
    });

    mswTest("latest download link points to correct GitHub release URL", async () => {
        await renderAppRoute("/downloads");

        // The latest download image links to the GitHub release
        await expect
            .poll(() => {
                const img = document.querySelector(
                    'img[alt="Download for Linux"], img[alt="Download for Windows"], img[alt="Download for Mac"]',
                );
                const link = img?.closest("a");
                return link
                    ?.getAttribute("href")
                    ?.includes("github.com/Amund211/prism/releases/download/v1.11.0");
            })
            .toBe(true);
    });

    mswTest("archive download links have download attribute", async () => {
        await renderAppRoute("/downloads");

        await expect
            .poll(() => {
                const links = document.querySelectorAll(
                    'a[href*="github.com/Amund211/prism/releases"]',
                );
                return [...links].every((link) => link.hasAttribute("download"));
            })
            .toBe(true);
    });
});
