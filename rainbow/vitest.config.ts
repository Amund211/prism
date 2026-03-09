import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
    resolve: {
        alias: { "#": path.resolve(import.meta.dirname, "src") },
    },
    test: {
        coverage: {
            provider: "v8",
            include: ["src/**/*.{ts,tsx}"],
            exclude: ["src/routeTree.gen.ts"],
        },
    },
});
