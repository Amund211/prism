import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// import { reactClickToComponent } from "vite-plugin-react-click-to-component";
import path from "node:path";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  return {
    plugins: [
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
      alias: { "@": path.resolve(__dirname, "src") },
    },
    ...((mode === "proxy-staging" || mode === "proxy-production") && {
      server: {
        port: 5173,
        open: true,
        proxy: {
          "/flashlight": {
            target:
              mode === "proxy-production"
                ? "https://flashlight.recdep.com"
                : "https://flashlight-test.recdep.com",
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
