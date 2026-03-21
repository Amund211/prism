import { render } from "vitest-browser-react";

import { createRouter } from "@tanstack/react-router";
import { QueryClient } from "@tanstack/react-query";
import { routeTree } from "../routeTree.gen.ts";
import App from "#App.tsx";

function createQueryClient() {
    return new QueryClient({
        defaultOptions: {
            queries: { retry: false, gcTime: 0 },
        },
    });
}

/**
 * Render the real app, starting at a specific URL.
 */
export async function renderAppRoute(initialEntry: string) {
    const queryClient = createQueryClient();

    // Create a new isolated router tied to the browser history
    // NOTE: Not sure if this matters, or if we could just use the real router
    const router = createRouter({ routeTree });

    window.history.pushState({}, "", initialEntry);

    const screen = await render(
        <App router={router} queryClient={queryClient} />,
    );
    return { screen, queryClient, router };
}
