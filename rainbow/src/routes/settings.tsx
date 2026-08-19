import { InfoOutlined } from "@mui/icons-material";
import { Stack, Tooltip, Typography } from "@mui/material";
import { createFileRoute } from "@tanstack/react-router";
import React from "react";

import { UserMultiSelect } from "#components/UserSearch.tsx";
import { useCurrentUser } from "#contexts/CurrentUser/hooks.ts";

function RouteComponent() {
    const { currentUser, setCurrentUser } = useCurrentUser();
    // Stable identity: UserMultiSelect passes `uuids` straight to MUI's
    // Autocomplete as its `value`, and MUI clears the search input whenever that
    // identity changes -- even mid-typing.
    const defaultPlayerUUIDs = React.useMemo(
        () => (currentUser !== null ? [currentUser] : []),
        [currentUser],
    );
    return (
        <Stack
            sx={{
                gap: 1,
            }}
        >
            <meta
                name="description"
                content="Change your settings for the Prism Overlay stats website. Set a default player to view your stats."
            />
            <link rel="canonical" href="https://prismoverlay.com/settings" />
            <Stack
                component="label"
                direction="row"
                sx={{
                    gap: 2,
                    alignItems: "center",
                }}
            >
                <Typography variant="h6">Default player</Typography>
                <Tooltip title="Your default player for the Prism Overlay website. Typically your own main account. You can still view the stats of other players.">
                    <InfoOutlined />
                </Tooltip>
            </Stack>
            <UserMultiSelect
                placeholder="Set default player"
                uuids={defaultPlayerUUIDs}
                onSubmit={(uuids) => {
                    const newDefault = uuids.at(-1) ?? null;

                    setCurrentUser(newDefault);
                }}
            />
        </Stack>
    );
}

export const Route = createFileRoute("/settings")({
    component: RouteComponent,
});
