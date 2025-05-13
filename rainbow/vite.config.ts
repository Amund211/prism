import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { reactClickToComponent } from "vite-plugin-react-click-to-component";
import path from "node:path";
import { TanStackRouterVite } from "@tanstack/router-plugin/vite";
import { sentryVitePlugin } from "@sentry/vite-plugin";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
    return {
        build: {
            sourcemap: true,
        },
        plugins: [
            TanStackRouterVite({
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
                        target:
                            mode === "proxy-production"
                                ? "https://flashlight-cr-184945651621.northamerica-northeast2.run.app"
                                : "https://flashlight-test-cr-184945651621.northamerica-northeast2.run.app",
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
