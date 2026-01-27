import { UserSearch } from "#components/UserSearch.tsx";
import { Stack } from "@mui/material";
import { createFileRoute } from "@tanstack/react-router";
import { usePlayerVisits } from "#contexts/PlayerVisits/hooks.ts";
import { captureException } from "@sentry/react";

export const Route = createFileRoute("/session/")({
    component: RouteComponent,
});

function RouteComponent() {
    const navigate = Route.useNavigate();
    const { visitPlayer } = usePlayerVisits();

    return (
        <Stack spacing={1}>
            <meta
                name="description"
                content="Search for player's session stats, including daily, weekly, and monthly stats, as well as a progression towards stat milestones, and individual session breakdowns."
            />
            <link rel="canonical" href="https://prismoverlay.com/session" />
            <UserSearch
                onSubmit={(uuid) => {
                    visitPlayer(uuid);
                    navigate({
                        from: "/session/",
                        to: "/session/$uuid",
                        params: { uuid },
                        search: {
                            gamemode: "overall",
                            stat: "fkdr",
                            timeIntervalDefinition: { type: "contained" },
                            variantSelection: "both",
                            sessionTableMode: "total",
                            showExtrapolatedSessions: false,
                        },
                    }).catch((error: unknown) => {
                        captureException(error, {
                            tags: {
                                param: "uuid",
                            },
                            extra: {
                                message: "Failed to update search params",
                                uuid,
                            },
                        });
                    });
                }}
            />
        </Stack>
    );
}
