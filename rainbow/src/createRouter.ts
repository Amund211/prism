import type { QueryClient } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";

import { routeTree } from "./routeTree.gen.ts";

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
