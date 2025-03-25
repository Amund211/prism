import { createFileRoute } from "@tanstack/react-router";
import { Stack } from "@mui/material";
import { UserSearch } from "#components/UserSearch.tsx";

export const Route = createFileRoute("/")({
    component: RouteComponent,
});

function RouteComponent() {
    const navigate = Route.useNavigate();

    return (
        <Stack
            height="100%"
            width="100%"
            justifyContent="center"
            alignItems="center"
        >
            <meta
                name="description"
                content="The Prism Overlay for Hypixel Bedwars shows the stats of all players in your game and automatically tracks your progress. View your session stats and compare your stats with other players."
            />
            <UserSearch
                onSubmit={(uuid) => {
                    navigate({
                        to: "/session",
                        search: {
                            uuid,
                            gamemode: "overall",
                            stat: "fkdr",
                            timeIntervalDefinition: { type: "contained" },
                            variantSelection: "both",
                            sessionTableMode: "total",
                        },
                    }).catch((error: unknown) => {
                        // TODO: Handle error
                        console.error(
                            "Failed to update search params: gamemode",
                            error,
                        );
                    });
                }}
                size="medium"
            />
        </Stack>
    );
}
