import { Stack } from "@mui/material";
import { captureException } from "@sentry/react";
import { createFileRoute } from "@tanstack/react-router";

import { UserSearch } from "#components/UserSearch.tsx";
import { usePlayerVisits } from "#contexts/PlayerVisits/hooks.ts";
import { getWrappedYear } from "#helpers/wrapped.ts";

export const Route = createFileRoute("/wrapped/")({
    // oxlint-disable-next-line eslint/no-use-before-define
    component: RouteComponent,
});

function RouteComponent() {
    const navigate = Route.useNavigate();
    const { visitPlayer } = usePlayerVisits();

    return (
        <Stack spacing={1}>
            <meta
                name="description"
                content="View a summary of a player's Bed Wars stats for the past year, showcasing their achievements, milestones, and highlights."
            />
            <link rel="canonical" href="https://prismoverlay.com/wrapped" />
            <UserSearch
                onSubmit={(uuid) => {
                    visitPlayer(uuid);
                    void (async () => {
                        try {
                            await navigate({
                                from: "/wrapped/",
                                to: "/wrapped/$uuid",
                                params: { uuid },
                                search: {
                                    year: getWrappedYear(),
                                },
                            });
                        } catch (error: unknown) {
                            captureException(error, {
                                tags: {
                                    param: "uuid",
                                },
                                extra: {
                                    message: "Failed to update search params",
                                    uuid,
                                },
                            });
                        }
                    })();
                }}
            />
        </Stack>
    );
}
