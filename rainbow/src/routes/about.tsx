import { AccountCircle } from "@mui/icons-material";
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
            <Discord />
            <Thanks />
            <Disclaimer />
            <HypixelAPIPolicy />
            <Privacy />
        </Stack>
    );
}

const Discord = () => {
    return (
        <Stack>
            <Typography variant="h6">Discord</Typography>
            <Typography variant="body1">
                <a
                    href="https://discord.gg/k4FGUnEHYg"
                    target="_blank"
                    rel="noreferrer"
                >
                    Join our Discord server
                </a>{" "}
                to get support and share your ideas!
            </Typography>
        </Stack>
    );
};

const Thanks = () => {
    return (
        <Stack>
            <Typography variant="h6">Thanks</Typography>
            <List>
                <ListItem>
                    <ListItemIcon>
                        <AccountCircle />
                    </ListItemIcon>
                    <ListItemText>
                        <a
                            href="https://crafatar.com"
                            target="_blank"
                            rel="noreferrer"
                        >
                            Crafatar
                        </a>{" "}
                        for providing avatars.
                    </ListItemText>
                </ListItem>
            </List>
        </Stack>
    );
};

const Disclaimer = () => {
    return (
        <Stack>
            <Typography variant="h6">Disclaimer</Typography>
            <Typography variant="body1">
                Prism Overlay is not associated with or endorsed by Mojang
                Studios or The Hypixel Network.
            </Typography>
        </Stack>
    );
};

const HypixelAPIPolicy = () => {
    return (
        <Stack>
            <Typography variant="h6">Hypixel API Policy</Typography>
            <Stack gap={1}>
                <Typography variant="body1">
                    The Prism Overlay project strives to stay within the bounds
                    of the{" "}
                    <a
                        href="https://developer.hypixel.net/policies/"
                        target="_blank"
                        rel="noreferrer"
                    >
                        Hypixel API policy
                    </a>
                    . Prism Overlay does <strong>not</strong> do automatic
                    polling of player stats. When users check their stats on the
                    website, the stats are persisted to a database and the
                    persisted copies of the stats are the basis for the tracking
                    shown on the website.
                </Typography>
                <Typography variant="body1">
                    Created by Skydeath (a937646b-f115-44c3-8dbf-9ae4a65669a0)
                </Typography>
            </Stack>
        </Stack>
    );
};

const Privacy = () => {
    return (
        <Stack>
            <Typography variant="h6">Privacy</Typography>
            <Typography variant="body1">
                Prism Overlay does not collect any personal data. Player stats
                fetched by the overlay and the website are stored to enable the
                tracking functionality on the website. If you don&apos;t want
                your statistics available on the website, please create a ticket
                on{" "}
                <a
                    href="https://discord.gg/k4FGUnEHYg"
                    target="_blank"
                    rel="noreferrer"
                >
                    Discord
                </a>
                .
            </Typography>
        </Stack>
    );
};
