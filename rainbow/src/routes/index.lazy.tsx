import { Stack } from "@mui/material";
import { createLazyFileRoute, getRouteApi } from "@tanstack/react-router";
import { UserSearch } from "#components/UserSearch.tsx";

export const Route = createLazyFileRoute("/")({
    component: RouteComponent,
});

const route = getRouteApi("/");

function RouteComponent() {
    const navigate = route.useNavigate();

    return (
        <Stack
            height="100%"
            width="100%"
            justifyContent="center"
            alignItems="center"
        >
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
