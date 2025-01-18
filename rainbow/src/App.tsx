import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createRouter } from "@tanstack/react-router";
import { queryClient } from "#queryClient.ts";
//
// Import the generated route tree
import { routeTree } from "./routeTree.gen.ts";

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
        <QueryClientProvider client={queryClient}>
            <RouterProvider router={router} />
        </QueryClientProvider>
    );
}

export default App;
