import { defineConfig } from "vitest/config";
import path from "node:path";
import react from "@vitejs/plugin-react";
import { playwright } from "@vitest/browser-playwright";

const IS_CI = !!process.env.CI;

const USE_LOCAL_BROWSER = !IS_CI;

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
                            timeout: 10_000,
                        },
                    },
                    browser: {
                        enabled: true,
                        provider: playwright(),
                        // https://vitest.dev/config/browser/playwright
                        instances: USE_LOCAL_BROWSER
                            ? [
                                  { browser: "chromium" },
                                  // { browser: "webkit" },
                                  // { browser: "firefox" },
                                  /*
                                  {
                                      browser: "chromium",
                                      provider: playwright({
                                          launchOptions: {
                                              executablePath:
                                                  "/usr/bin/chromium",
                                          },
                                      }),
                                  },
                                  */
                                  /*
                                  {
                                      browser: "firefox",
                                      provider: playwright({
                                          launchOptions: {
                                              executablePath:
                                                  "/usr/bin/firefox",
                                          },
                                      }),
                                  },
                                */
                              ]
                            : [
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
