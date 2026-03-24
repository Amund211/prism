import { createRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen.ts";
import type { QueryClient } from "@tanstack/react-query";

export function createAppRouter(queryClient: QueryClient) {
    return createRouter({
        routeTree,
        defaultPreload: "intent",
        context: { queryClient },
    });
}

export type AppRouter = ReturnType<typeof createAppRouter>;

declare module "@tanstack/react-router" {
    interface Register {
        router: AppRouter;
    }
}
