import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// import { reactClickToComponent } from "vite-plugin-react-click-to-component";
import path from "node:path";
import { TanStackRouterVite } from "@tanstack/router-plugin/vite";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
    return {
        plugins: [
            TanStackRouterVite(),
            react(),
            /*
      (mode === "development" ||
        mode === "proxy-staging" ||
        mode === "proxy-production") &&
        reactClickToComponent(),
        */
        ],
        /**
         * Import alias, enables imports such as
         * import { AppLayout } from "@/components/Layouts";
         * rather than relative imports.
         *
         * Should be used in conjunction with the `"paths"` field in `tsconfig.json`
         */
        resolve: {
            alias: { "@": path.resolve(import.meta.dirname, "src") },
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
                    "/mojang": {
                        target: "https://sessionserver.mojang.com",
                        changeOrigin: true,
                        cookieDomainRewrite: {
                            "*": "localhost",
                        },
                        rewrite: (path) => path.replace(/^\/mojang\//, "/"),
                    },
                },
            },
        }),
    };
});
