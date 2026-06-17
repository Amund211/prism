import path from "node:path";

import react from "@vitejs/plugin-react";
import { playwright } from "@vitest/browser-playwright";
import { defineConfig } from "vitest/config";

export default defineConfig({
    resolve: {
        alias: { "#": path.resolve(import.meta.dirname, "src") },
    },
    test: {
        includeTaskLocation: true,
        coverage: {
            provider: "v8",
            include: ["src/**/*.{ts,tsx}"],
            exclude: ["src/routeTree.gen.ts"],
        },
        projects: [
            {
                extends: true,
                test: {
                    name: "unit",
                    include: ["src/**/*.unit.test.ts"],
                },
            },
            {
                extends: true,
                plugins: [react()],
                test: {
                    name: "ui",
                    include: ["src/**/*.ui.test.tsx"],
                    setupFiles: ["./src/test/setup.ts"],

                    // CI machines are slower and require higher timeouts
                    testTimeout: 60_000,
                    expect: {
                        poll: {
                            timeout: 20_000,
                        },
                    },
                    browser: {
                        enabled: true,
                        provider: playwright(),
                        // https://vitest.dev/config/browser/playwright
                        //
                        // All supported browsers are defined here. By default
                        // the test scripts filter to chromium with
                        // `--browser=chromium` (see package.json). To run a
                        // different browser locally, pass `--browser=webkit`
                        // (e.g. `pnpm run test:ui:webkit`).
                        instances: [
                            { browser: "chromium" },
                            { browser: "webkit" },
                            // Firefox does not seem to work well with msw
                            // https://mswjs.io/docs/limitations/
                            // { browser: "firefox" },
                        ],
                    },
                },
            },
        ],
    },
});
