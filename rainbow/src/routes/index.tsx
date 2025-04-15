import { createFileRoute, createLink } from "@tanstack/react-router";
import { Avatar, Button, IconButton, Stack, Typography } from "@mui/material";
import { UserSearch } from "#components/UserSearch.tsx";
import { useUUIDToUsername } from "#queries/username.ts";
import { Delete } from "@mui/icons-material";
import { usePlayerVisits } from "#contexts/PlayerVisits/hooks.ts";
import { useCurrentUser } from "#contexts/CurrentUser/hooks.ts";

const RouterLinkButton = createLink(Button);

export const Route = createFileRoute("/")({
    component: RouteComponent,
});

function RouteComponent() {
    const navigate = Route.useNavigate();
    const { currentUser } = useCurrentUser();
    const { favoriteUUIDs, removePlayerVisits } = usePlayerVisits();
    const favorites = currentUser
        ? [
              currentUser,
              ...favoriteUUIDs.filter((uuid) => uuid !== currentUser),
          ].slice(0, 5)
        : favoriteUUIDs.slice(0, 5);
    const uuidToUsername = useUUIDToUsername(favorites);

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
            <link rel="canonical" href="https://prismoverlay.com" />
            <UserSearch
                onSubmit={(uuid) => {
                    navigate({
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
                            to="/session/$uuid"
                            params={{ uuid }}
                            search={{
                                gamemode: "overall",
                                stat: "fkdr",
                                timeIntervalDefinition: { type: "contained" },
                                variantSelection: "both",
                                sessionTableMode: "total",
                                showExtrapolatedSessions: false,
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
                                    "&:hover": {
                                        transition: "opacity 0.2s",
                                        opacity: "1!important",
                                    },
                                    "&:focus": {
                                        transition: "opacity 0.2s",
                                        opacity: "1!important",
                                    },
                                }}
                                size="small"
                                color="error"
                                onClick={(event) => {
                                    event.stopPropagation();
                                    event.preventDefault();
                                    removePlayerVisits(uuid);
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
