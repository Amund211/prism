import { CssBaseline } from "@mui/material";
import { RouterProvider, createRouter } from "@tanstack/react-router";
import { maxAge, persister, queryClient } from "#queryClient.ts";
import { routeTree } from "./routeTree.gen.ts";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";

// Create a new router instance
const router = createRouter({ routeTree, defaultPreload: "intent" });

// Register the router instance for type safety
declare module "@tanstack/react-router" {
    interface Register {
        router: typeof router;
    }
}

function App() {
    return (
        <PersistQueryClientProvider
            client={queryClient}
            persistOptions={{
                persister,
                maxAge,
            }}
        >
            <CssBaseline />
            <RouterProvider router={router} />
        </PersistQueryClientProvider>
    );
}

export default App;
