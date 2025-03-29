import { createFileRoute, createLink } from "@tanstack/react-router";
import { Avatar, Button, IconButton, Stack, Typography } from "@mui/material";
import { UserSearch } from "#components/UserSearch.tsx";
import {
    removeFavoritePlayer,
    useFavoritePlayers,
} from "#hooks/useFavoritePlayers.ts";
import { useUUIDToUsername } from "#queries/username.ts";
import { Delete } from "@mui/icons-material";
import React from "react";

const RouterLinkButton = createLink(Button);

export const Route = createFileRoute("/")({
    component: RouteComponent,
});

function RouteComponent() {
    const navigate = Route.useNavigate();
    const favorites = useFavoritePlayers(5);
    const uuidToUsername = useUUIDToUsername(favorites);
    const [, rerender] = React.useReducer(() => ({}), {});

    return (
        <Stack
            height="100%"
            width="100%"
            justifyContent="center"
            alignItems="center"
            gap={2}
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
            {favorites.length > 0 && (
                <Stack direction="row" gap={1}>
                    {favorites.map((uuid) => (
                        <RouterLinkButton
                            sx={{
                                minWidth: 80,
                                textTransform: "none",
                                [`& #delete-favorite-${uuid}`]: {
                                    transition: "opacity 0.2s",
                                    opacity: 0,
                                },
                                [`&:hover #delete-favorite-${uuid}`]: {
                                    transition: "opacity 0.2s",
                                    opacity: 1,
                                },
                            }}
                            key={uuid}
                            to="/session"
                            search={{
                                uuid,
                                gamemode: "overall",
                                stat: "fkdr",
                                timeIntervalDefinition: { type: "contained" },
                                variantSelection: "both",
                                sessionTableMode: "total",
                            }}
                        >
                            <Stack alignItems="center" gap={1}>
                                <Avatar
                                    // TODO: Attribution - https://crafatar.com/#meta-attribution
                                    src={`https://crafatar.com/renders/head/${uuid}?overlay`}
                                    alt={`Player head of ${uuidToUsername[uuid] ?? "unknown"}`}
                                />
                                <Typography variant="body2">
                                    {uuidToUsername[uuid]}
                                </Typography>
                            </Stack>
                            <IconButton
                                id={`delete-favorite-${uuid}`}
                                sx={{
                                    position: "absolute",
                                    top: -5,
                                    right: -5,
                                }}
                                size="small"
                                color="error"
                                onClick={(event) => {
                                    event.stopPropagation();
                                    event.preventDefault();
                                    removeFavoritePlayer(uuid);
                                    rerender();
                                }}
                            >
                                <Delete
                                    fontSize="small"
                                    aria-label={`Remove ${uuidToUsername[uuid] ?? "unknown"} from favorites`}
                                />
                            </IconButton>
                        </RouterLinkButton>
                    ))}
                </Stack>
            )}
        </Stack>
    );
}
