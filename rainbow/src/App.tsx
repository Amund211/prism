import { createTheme, CssBaseline, ThemeProvider } from "@mui/material";
import { RouterProvider, createRouter } from "@tanstack/react-router";
import { maxAge, persister, queryClient } from "#queryClient.ts";
import { routeTree } from "./routeTree.gen.ts";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import { LocalizationProvider } from "@mui/x-date-pickers";
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs";
import { CurrentUserProvider } from "#contexts/CurrentUser/provider.tsx";

// Create a new router instance
const router = createRouter({ routeTree, defaultPreload: "intent" });

// Register the router instance for type safety
declare module "@tanstack/react-router" {
    interface Register {
        router: typeof router;
    }
}

const theme = createTheme({
    colorSchemes: {
        dark: true,
    },
});

function App() {
    return (
        <PersistQueryClientProvider
            client={queryClient}
            persistOptions={{
                persister,
                maxAge,
            }}
        >
            <LocalizationProvider dateAdapter={AdapterDayjs}>
                <ThemeProvider theme={theme} noSsr>
                    <CurrentUserProvider>
                        <CssBaseline />
                        <RouterProvider router={router} />
                    </CurrentUserProvider>
                </ThemeProvider>
            </LocalizationProvider>
        </PersistQueryClientProvider>
    );
}

export default App;
