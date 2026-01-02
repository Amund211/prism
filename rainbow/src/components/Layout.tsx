import {
    CalendarMonth,
    Download,
    Info,
    Menu as MenuIcon,
    MenuOpen,
    Redeem,
    Settings,
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
import {
    createLink,
    Link,
    useLocation,
    useRouterState,
} from "@tanstack/react-router";
import React from "react";
import { DarkModeSwitch } from "./DarkModeSwitch.tsx";
import { endOfMonth, startOfMonth } from "#intervals.ts";
import { useCurrentUser } from "#contexts/CurrentUser/hooks.ts";
import { getWrappedYear } from "#helpers/wrapped.ts";

const RouterLinkItemButton = createLink(ListItemButton);
const RouterMenuItem = createLink(MenuItem);

const APP_BAR_HEIGHT_PX = "64px";

/**
 * Get the UUID of the currently shown player based on the current route.
 * Returns the UUID from route params for session/wrapped pages,
 * or the first UUID from the history explorer.
 * Returns null if not viewing a player-specific page.
 */
function useShownPlayer(): string | null {
    const routerState = useRouterState();

    if (routerState.matches.length === 0) {
        return null;
    }

    const currentMatch = routerState.matches[routerState.matches.length - 1];

    switch (currentMatch.routeId) {
        case "/session/$uuid":
        case "/wrapped/$uuid":
            return currentMatch.params.uuid;
        case "/history/explore": {
            const uuids = currentMatch.search.uuids;
            return uuids.length > 0 ? uuids[0] : null;
        }
        case "__root__":
        case "/":
        case "/about":
        case "/downloads":
        case "/settings":
        case "/session/":
        case "/wrapped/":
            return null;
        default:
            currentMatch satisfies never;
            return null; // Unreachable
    }
}

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

    const { currentUser } = useCurrentUser();
    const shownPlayer = useShownPlayer();
    const playerToNavigate = shownPlayer ?? currentUser;

    const now = new Date();

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
                        <Link to="/" style={{ textDecoration: "none" }}>
                            <Stack direction="row" gap={1} alignItems="center">
                                <img
                                    src="/who.png"
                                    alt="Prism Overlay logo"
                                    width="40"
                                    height="40"
                                />
                                <Typography variant="h6" color="textPrimary">
                                    Prism Overlay
                                </Typography>
                            </Stack>
                        </Link>
                        <Stack direction="row" gap={1}>
                            <DarkModeSwitch />
                            <IconButton
                                onClick={handleClickMenu}
                                aria-label="Open toolbar menu"
                            >
                                {menuOpen ? <MenuOpen /> : <MenuIcon />}
                            </IconButton>
                        </Stack>
                        <Menu
                            open={menuOpen}
                            anchorEl={anchorEl}
                            onClose={handleCloseMenu}
                        >
                            {playerToNavigate ? (
                                <RouterMenuItem
                                    to="/session/$uuid"
                                    selected={location.pathname.startsWith(
                                        "/session",
                                    )}
                                    params={{ uuid: playerToNavigate }}
                                    search={{
                                        timeIntervalDefinition: {
                                            type: "contained",
                                        },
                                        gamemode: "overall",
                                        stat: "fkdr",
                                        variantSelection: "both",
                                        sessionTableMode: "total",
                                        showExtrapolatedSessions: false,
                                    }}
                                    onClick={handleCloseMenu}
                                >
                                    <ListItemIcon>
                                        <TrendingUp />
                                    </ListItemIcon>
                                    <ListItemText primary="Session stats" />
                                </RouterMenuItem>
                            ) : (
                                <RouterMenuItem
                                    to="/session"
                                    selected={location.pathname.startsWith(
                                        "/session",
                                    )}
                                    onClick={handleCloseMenu}
                                >
                                    <ListItemIcon>
                                        <TrendingUp />
                                    </ListItemIcon>
                                    <ListItemText primary="Session stats" />
                                </RouterMenuItem>
                            )}
                            <RouterMenuItem
                                to="/history/explore"
                                selected={
                                    location.pathname === "/history/explore"
                                }
                                search={{
                                    uuids: playerToNavigate
                                        ? [playerToNavigate]
                                        : [],
                                    start: startOfMonth(now),
                                    end: endOfMonth(now),
                                    limit: 100,
                                    stats: ["fkdr"],
                                    gamemodes: ["overall"],
                                    variantSelection: "both",
                                }}
                                onClick={handleCloseMenu}
                            >
                                <ListItemIcon>
                                    <CalendarMonth />
                                </ListItemIcon>
                                <ListItemText primary="History explorer" />
                            </RouterMenuItem>
                            {playerToNavigate ? (
                                <RouterMenuItem
                                    to="/wrapped/$uuid"
                                    selected={location.pathname.startsWith(
                                        "/wrapped",
                                    )}
                                    params={{ uuid: playerToNavigate }}
                                    search={{ year: getWrappedYear() }}
                                    onClick={handleCloseMenu}
                                >
                                    <ListItemIcon>
                                        <Redeem />
                                    </ListItemIcon>
                                    <ListItemText
                                        primary={`Wrapped ${getWrappedYear().toString()}`}
                                    />
                                </RouterMenuItem>
                            ) : (
                                <RouterMenuItem
                                    to="/wrapped"
                                    selected={location.pathname.startsWith(
                                        "/wrapped",
                                    )}
                                    onClick={handleCloseMenu}
                                >
                                    <ListItemIcon>
                                        <Redeem />
                                    </ListItemIcon>
                                    <ListItemText
                                        primary={`Wrapped ${getWrappedYear().toString()}`}
                                    />
                                </RouterMenuItem>
                            )}
                            <RouterMenuItem
                                selected={location.pathname === "/downloads"}
                                to="/downloads"
                                onClick={handleCloseMenu}
                            >
                                <ListItemIcon>
                                    <Download />
                                </ListItemIcon>
                                <ListItemText primary="Downloads" />
                            </RouterMenuItem>
                            <RouterMenuItem
                                selected={location.pathname === "/settings"}
                                to="/settings"
                                onClick={handleCloseMenu}
                            >
                                <ListItemIcon>
                                    <Settings />
                                </ListItemIcon>
                                <ListItemText primary="Settings" />
                            </RouterMenuItem>
                            <RouterMenuItem
                                selected={location.pathname === "/about"}
                                to="/about"
                                onClick={handleCloseMenu}
                            >
                                <ListItemIcon>
                                    <Info />
                                </ListItemIcon>
                                <ListItemText primary="About" />
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
                <Link to="/" style={{ textDecoration: "none" }}>
                    <Stack
                        direction="row"
                        paddingY={1.5}
                        paddingX={3}
                        gap={1}
                        alignItems="center"
                    >
                        <img
                            src="/who.png"
                            alt="Prism Overlay logo"
                            width="40"
                            height="40"
                        />
                        <Typography variant="h6" color="textPrimary">
                            Prism Overlay
                        </Typography>
                    </Stack>
                </Link>
                <Divider />
                <Stack height="100%" overflow="auto">
                    <List dense component="menu">
                        <ListItem disablePadding>
                            {playerToNavigate ? (
                                <RouterLinkItemButton
                                    selected={location.pathname.startsWith(
                                        "/session",
                                    )}
                                    to="/session/$uuid"
                                    params={{ uuid: playerToNavigate }}
                                    search={{
                                        timeIntervalDefinition: {
                                            type: "contained",
                                        },
                                        gamemode: "overall",
                                        stat: "fkdr",
                                        variantSelection: "both",
                                        sessionTableMode: "total",
                                        showExtrapolatedSessions: false,
                                    }}
                                >
                                    <ListItemIcon>
                                        <TrendingUp />
                                    </ListItemIcon>
                                    <ListItemText primary="Session stats" />
                                </RouterLinkItemButton>
                            ) : (
                                <RouterLinkItemButton
                                    selected={location.pathname.startsWith(
                                        "/session",
                                    )}
                                    to="/session"
                                >
                                    <ListItemIcon>
                                        <TrendingUp />
                                    </ListItemIcon>
                                    <ListItemText primary="Session stats" />
                                </RouterLinkItemButton>
                            )}
                        </ListItem>
                        <ListItem disablePadding>
                            <RouterLinkItemButton
                                selected={
                                    location.pathname === "/history/explore"
                                }
                                to="/history/explore"
                                search={{
                                    uuids: playerToNavigate
                                        ? [playerToNavigate]
                                        : [],
                                    start: startOfMonth(now),
                                    end: endOfMonth(now),
                                    limit: 100,
                                    stats: ["fkdr"],
                                    gamemodes: ["overall"],
                                    variantSelection: "both",
                                }}
                            >
                                <ListItemIcon>
                                    <CalendarMonth />
                                </ListItemIcon>
                                <ListItemText primary="History explorer" />
                            </RouterLinkItemButton>
                        </ListItem>
                        <ListItem disablePadding>
                            {playerToNavigate ? (
                                <RouterLinkItemButton
                                    selected={location.pathname.startsWith(
                                        "/wrapped",
                                    )}
                                    to="/wrapped/$uuid"
                                    params={{ uuid: playerToNavigate }}
                                    search={{ year: getWrappedYear() }}
                                >
                                    <ListItemIcon>
                                        <Redeem />
                                    </ListItemIcon>
                                    <ListItemText
                                        primary={`Wrapped ${getWrappedYear().toString()}`}
                                    />
                                </RouterLinkItemButton>
                            ) : (
                                <RouterLinkItemButton
                                    selected={location.pathname.startsWith(
                                        "/wrapped",
                                    )}
                                    to="/wrapped"
                                >
                                    <ListItemIcon>
                                        <Redeem />
                                    </ListItemIcon>
                                    <ListItemText
                                        primary={`Wrapped ${getWrappedYear().toString()}`}
                                    />
                                </RouterLinkItemButton>
                            )}
                        </ListItem>
                        <ListItem disablePadding>
                            <RouterLinkItemButton
                                selected={location.pathname === "/downloads"}
                                to="/downloads"
                            >
                                <ListItemIcon>
                                    <Download />
                                </ListItemIcon>
                                <ListItemText primary="Downloads" />
                            </RouterLinkItemButton>
                        </ListItem>
                        <ListItem disablePadding>
                            <RouterLinkItemButton
                                selected={location.pathname === "/settings"}
                                to="/settings"
                            >
                                <ListItemIcon>
                                    <Settings />
                                </ListItemIcon>
                                <ListItemText primary="Settings" />
                            </RouterLinkItemButton>
                        </ListItem>
                        <ListItem disablePadding>
                            <RouterLinkItemButton
                                selected={location.pathname === "/about"}
                                to="/about"
                            >
                                <ListItemIcon>
                                    <Info />
                                </ListItemIcon>
                                <ListItemText primary="About" />
                            </RouterLinkItemButton>
                        </ListItem>
                    </List>
                </Stack>
                <Divider />
                <Stack padding={1} justifyContent="center" alignItems="center">
                    <DarkModeSwitch />
                </Stack>
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
