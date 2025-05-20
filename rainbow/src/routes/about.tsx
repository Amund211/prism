import { AccountCircle, Badge } from "@mui/icons-material";
import {
    List,
    ListItem,
    ListItemIcon,
    ListItemText,
    Stack,
    Typography,
} from "@mui/material";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/about")({
    component: RouteComponent,
});

function RouteComponent() {
    return (
        <Stack gap={3}>
            <meta
                name="description"
                content="Learn more about the Prism Overlay, a tool for Hypixel Bedwars that shows the stats of all players in your game and automatically tracks your progress. Use it to view your session stats and compare your stats with other players."
            />
            <link rel="canonical" href="https://prismoverlay.com/about" />
            <Stack>
                <Typography variant="h6">Thanks</Typography>
                <List>
                    <ListItem>
                        <ListItemIcon>
                            <AccountCircle />
                        </ListItemIcon>
                        <ListItemText>
                            <a href="https://crafatar.com">Crafatar</a> for
                            providing avatars.
                        </ListItemText>
                    </ListItem>
                    <ListItem>
                        <ListItemIcon>
                            <Badge />
                        </ListItemIcon>
                        <ListItemText>
                            <a href="https://api.minetools.eu/">MineTools</a>{" "}
                            for providing UUID/username conversion.
                        </ListItemText>
                    </ListItem>
                </List>
            </Stack>

            <Stack>
                <Typography variant="h6">Disclaimer</Typography>
                <Typography variant="body1">
                    Prism Overlay is not associated with or endorsed by Mojang
                    Studios or The Hypixel Network.
                </Typography>
            </Stack>
        </Stack>
    );
}
