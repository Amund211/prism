import { UserMultiSelect } from "#components/UserSearch.tsx";
import { useCurrentUser } from "#contexts/CurrentUser/hooks.ts";
import { InfoOutlined } from "@mui/icons-material";
import { Stack, Tooltip, Typography } from "@mui/material";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/settings")({
    component: RouteComponent,
});

function RouteComponent() {
    const { currentUser, setCurrentUser } = useCurrentUser();
    return (
        <Stack gap={1}>
            <meta
                name="description"
                content="Change your settings for the Prism Overlay stats website. Set a default player to view your stats."
            />
            <link rel="canonical" href="https://prismoverlay.com/settings" />
            <Stack
                component="label"
                direction="row"
                gap={2}
                alignItems="center"
            >
                <Typography variant="h6">Default player</Typography>
                <Tooltip title="Your default player for the Prism Overlay website. Typically your own main account. You can still view the stats of other players.">
                    <InfoOutlined />
                </Tooltip>
            </Stack>
            <UserMultiSelect
                placeholder="Set default player"
                uuids={currentUser ? [currentUser] : []}
                onSubmit={(uuids) => {
                    const newDefault = uuids[uuids.length - 1] ?? null;

                    setCurrentUser(newDefault);
                }}
            />
        </Stack>
    );
}
