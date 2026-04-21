import { createTheme, CssBaseline, ThemeProvider } from "@mui/material";
import { LocalizationProvider } from "@mui/x-date-pickers";
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs";
import type { QueryClient } from "@tanstack/react-query";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import type { Persister } from "@tanstack/react-query-persist-client";
import { RouterProvider } from "@tanstack/react-router";

import { CurrentUserProvider } from "#contexts/CurrentUser/provider.tsx";
import { KnownAliasesProvider } from "#contexts/KnownAliases/provider.tsx";
import { PlayerVisitsProvider } from "#contexts/PlayerVisits/provider.tsx";
import type { AppRouter } from "#createRouter.ts";
import { maxAge } from "#queryClient.ts";

const theme = createTheme({
    colorSchemes: {
        dark: true,
    },
});

interface AppProps {
    readonly router: AppRouter;
    readonly queryClient: QueryClient;
    readonly persister: Persister;
}

export function App({ router, queryClient, persister }: AppProps) {
    return (
        <PersistQueryClientProvider
            client={queryClient}
            persistOptions={{
                persister,
                maxAge,
                buster: "1", // API version
            }}
        >
            <LocalizationProvider dateAdapter={AdapterDayjs}>
                <ThemeProvider theme={theme} noSsr>
                    <CurrentUserProvider>
                        <PlayerVisitsProvider>
                            <KnownAliasesProvider>
                                <CssBaseline />
                                <RouterProvider router={router} />
                            </KnownAliasesProvider>
                        </PlayerVisitsProvider>
                    </CurrentUserProvider>
                </ThemeProvider>
            </LocalizationProvider>
        </PersistQueryClientProvider>
    );
}
