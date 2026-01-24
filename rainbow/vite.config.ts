import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { reactClickToComponent } from "vite-plugin-react-click-to-component";
import path from "node:path";
import tanstackRouter from "@tanstack/router-plugin/vite";
import { sentryVitePlugin } from "@sentry/vite-plugin";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
    return {
        build: {
            sourcemap: true,
        },
        plugins: [
            tanstackRouter({
                addExtensions: true,
                autoCodeSplitting: true,
            }),
            react({
                babel: {
                    plugins: ["babel-plugin-react-compiler"],
                },
            }),
            (mode === "development" ||
                mode === "proxy-staging" ||
                mode === "proxy-production") &&
                reactClickToComponent(),
            sentryVitePlugin({
                authToken: process.env.SENTRY_AUTH_TOKEN,
                org: "prism-overlay",
                project: "rainbow",
                telemetry: false,
                bundleSizeOptimizations: {
                    excludeDebugStatements: true,
                    // Only relevant if you added `browserTracingIntegration`
                    excludeTracing: true,
                    // Only relevant if you added `replayIntegration`
                    excludeReplayIframe: true,
                    excludeReplayShadowDom: true,
                    excludeReplayWorker: true,
                },
            }),
        ],
        /**
         * Import alias, enables imports such as
         * import { AppLayout } from "#components/Layouts";
         * rather than relative imports.
         *
         * Should be used in conjunction with the `"paths"` field in `tsconfig.json`
         */
        resolve: {
            alias: { "#": path.resolve(import.meta.dirname, "src") },
        },
        ...((mode === "proxy-staging" || mode === "proxy-production") && {
            server: {
                port: 5173,
                open: true,
                proxy: {
                    "/flashlight": {
                        // NOTE: The flashlight API does **not** allow third-party access.
                        //       Do not send any requests to any endpoints without explicit permission.
                        //       Reach out on Discord for more information. https://discord.gg/k4FGUnEHYg
                        target:
                            mode === "proxy-production"
                                ? "https://flashlight.prismoverlay.com"
                                : "https://flashlight-test.prismoverlay.com",
                        changeOrigin: true,
                        cookieDomainRewrite: {
                            "*": "localhost",
                        },
                        rewrite: (path) => path.replace(/^\/flashlight\//, "/"),
                    },
                },
            },
        }),
    };
});
