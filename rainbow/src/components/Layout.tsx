import {
    CalendarMonth,
    Menu as MenuIcon,
    MenuOpen,
    TrendingUp,
} from "@mui/icons-material";
import {
    AppBar,
    Box,
    Divider,
    Drawer,
    drawerClasses,
    IconButton,
    List,
    ListItem,
    ListItemButton,
    ListItemIcon,
    ListItemText,
    Menu,
    MenuItem,
    Stack,
    Toolbar,
    Typography,
} from "@mui/material";
import { createLink, useLocation } from "@tanstack/react-router";
import React from "react";

const RouterLinkItemButton = createLink(ListItemButton);
const RouterMenuItem = createLink(MenuItem);

const APP_BAR_HEIGHT_PX = "64px";

export const Layout: React.FC<{ children: React.ReactNode }> = ({
    children,
}) => {
    const location = useLocation();
    const [anchorEl, setAnchorEl] = React.useState<null | HTMLElement>(null);
    const menuOpen = Boolean(anchorEl);
    const handleClickMenu = (event: React.MouseEvent<HTMLButtonElement>) => {
        setAnchorEl(event.currentTarget);
    };
    const handleCloseMenu = () => {
        setAnchorEl(null);
    };

    return (
        // Layout inspired by https://github.com/mui/material-ui/tree/v6.4.1/docs/data/material/getting-started/templates/dashboard
        <Box
            sx={{
                display: "flex",
                height: {
                    xs: `calc(100% - ${APP_BAR_HEIGHT_PX})`,
                    lg: "100%",
                },
            }}
        >
            <AppBar
                position="fixed"
                sx={{
                    display: { xs: "auto", lg: "none" },
                    boxShadow: 0,
                    bgcolor: "background.paper",
                    borderBottom: "1px solid",
                    borderColor: "divider",
                    height: APP_BAR_HEIGHT_PX,
                }}
            >
                <Toolbar variant="regular">
                    <Stack
                        direction="row"
                        spacing={2}
                        alignItems="center"
                        justifyContent="space-between"
                        width="100%"
                    >
                        {/*TODO: Link to "home"*/}
                        <Stack direction="row" gap={1} alignItems="center">
                            <img
                                src="/who.png"
                                alt="Prism Overlay logo"
                                width="40"
                            />
                            <Typography variant="h6" color="textPrimary">
                                Prism Overlay
                            </Typography>
                        </Stack>
                        <IconButton onClick={handleClickMenu}>
                            {menuOpen ? <MenuOpen /> : <MenuIcon />}
                        </IconButton>
                        <Menu
                            open={menuOpen}
                            anchorEl={anchorEl}
                            onClose={handleCloseMenu}
                        >
                            <RouterMenuItem
                                to="/session"
                                search={{
                                    uuid: "a937646b-f115-44c3-8dbf-9ae4a65669a0",
                                    timeIntervalDefinition: {
                                        type: "until",
                                        date: new Date(
                                            "2025-01-15T22:30:00+01:00",
                                        ),
                                    },
                                    gamemode: "overall",
                                    stat: "fkdr",
                                    variantSelection: "both",
                                }}
                            >
                                <ListItemIcon>
                                    <TrendingUp />
                                </ListItemIcon>
                                <ListItemText primary="Session stats" />
                            </RouterMenuItem>
                            <RouterMenuItem
                                to="/history/compare"
                                search={{
                                    uuids: [
                                        "a937646b-f115-44c3-8dbf-9ae4a65669a0", // Skydeath
                                        "ac04f297-f74c-44de-a24e-0083936ac59a", // USBB
                                        "062c373b-28de-4ec0-ab2c-0114e59e36ce", // Skydeaf
                                        "3d58a2de-3831-4a17-a305-67258295f81e", // iCiara
                                        "6bc1dd0f-f351-4c3d-b6cc-262e55b6e7aa", // HardcoreLizard
                                    ],
                                    start: new Date(
                                        "2025-01-15T19:55:00+01:00",
                                    ),
                                    end: new Date("2025-01-15T22:30:00+01:00"),
                                    limit: 100,
                                    stats: ["stars", "finalKills"],
                                    gamemodes: ["overall"],
                                    variants: ["session"],
                                }}
                            >
                                <ListItemIcon>
                                    <CalendarMonth />
                                </ListItemIcon>
                                <ListItemText primary="Compare history" />
                            </RouterMenuItem>
                        </Menu>
                    </Stack>
                </Toolbar>
            </AppBar>
            <Drawer
                variant="permanent"
                sx={{
                    width: 240,
                    flexShrink: 0,
                    boxSizing: "border-box",
                    mt: 10,
                    display: { xs: "none", lg: "block" },
                    [`& .${drawerClasses.paper}`]: {
                        backgroundColor: "background.paper",
                        width: 240,
                        boxSizing: "border-box",
                    },
                }}
            >
                {/*TODO: Link to "home"*/}
                <Stack
                    direction="row"
                    paddingY={1.5}
                    paddingX={3}
                    gap={1}
                    alignItems="center"
                >
                    <img src="/who.png" alt="Prism Overlay logo" width="40" />
                    <Typography variant="h6">Prism Overlay</Typography>
                </Stack>
                <Divider />
                <List dense component="menu">
                    <ListItem disablePadding>
                        <RouterLinkItemButton
                            selected={location.pathname === "/session"}
                            to="/session"
                            search={{
                                uuid: "a937646b-f115-44c3-8dbf-9ae4a65669a0",
                                timeIntervalDefinition: {
                                    type: "until",
                                    date: new Date("2025-01-15T22:30:00+01:00"),
                                },
                                gamemode: "overall",
                                stat: "fkdr",
                                variantSelection: "both",
                            }}
                        >
                            <ListItemIcon>
                                <TrendingUp />
                            </ListItemIcon>
                            <ListItemText primary="Session stats" />
                        </RouterLinkItemButton>
                    </ListItem>
                    <ListItem disablePadding>
                        <RouterLinkItemButton
                            selected={location.pathname === "/history/compare"}
                            to="/history/compare"
                            search={{
                                uuids: [
                                    "a937646b-f115-44c3-8dbf-9ae4a65669a0", // Skydeath
                                    "ac04f297-f74c-44de-a24e-0083936ac59a", // USBB
                                    "062c373b-28de-4ec0-ab2c-0114e59e36ce", // Skydeaf
                                    "3d58a2de-3831-4a17-a305-67258295f81e", // iCiara
                                    "6bc1dd0f-f351-4c3d-b6cc-262e55b6e7aa", // HardcoreLizard
                                ],
                                start: new Date("2025-01-15T19:55:00+01:00"),
                                end: new Date("2025-01-15T22:30:00+01:00"),
                                limit: 100,
                                stats: ["stars", "finalKills"],
                                gamemodes: ["overall"],
                                variants: ["session"],
                            }}
                        >
                            <ListItemIcon>
                                <CalendarMonth />
                            </ListItemIcon>
                            <ListItemText primary="Compare history" />
                        </RouterLinkItemButton>
                    </ListItem>
                </List>
            </Drawer>
            <Stack
                component="main"
                sx={{
                    marginTop: { xs: APP_BAR_HEIGHT_PX, lg: 0 },
                    width: "100%",
                    height: "100%",
                }}
                padding={1}
            >
                {children}
            </Stack>
        </Box>
    );
};
