import {
    CalendarMonth,
    Download,
    Gavel,
    Info,
    Menu as MenuIcon,
    MenuOpen,
    PrivacyTip,
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
import type { MenuItemProps } from "@mui/material";
import { createLink, Link, useLocation, useRouterState } from "@tanstack/react-router";
import React from "react";

import { useCurrentUser } from "#contexts/CurrentUser/hooks.ts";
import { getWrappedYear } from "#helpers/wrapped.ts";
import { endOfMonth, startOfMonth } from "#intervals.ts";

import { DarkModeSwitch } from "./DarkModeSwitch.tsx";

const RouterLinkItemButton = createLink(ListItemButton);

// `MenuItem` roots an `<li>`, and an `<li href>` is inert — the router's href
// lands on it, but middle-click and "open in new tab" do nothing. Pin
// `component="a"` here rather than at each call site: MUI's own `component`
// prop doesn't survive `createLink`'s prop types (cf. the cast the history
// explorer's `RouterLinkChip` needs). `role="menuitem"` is unaffected. The
// anchors do end up directly inside `MenuList`'s `<ul>`, which only permits
// `<li>` — MUI's own documented `component="a"` pattern has that wart too.
// MUI owns this prop shape, so the parameter cannot be made fully readonly.
// oxlint-disable-next-line typescript/prefer-readonly-parameter-types
const AnchorMenuItem = (props: MenuItemProps<"a">) => (
    <MenuItem
        // Spread first so `component` stays pinned: it is optional in
        // `MenuItemProps`, so a call site overriding it would silently go back
        // to an inert `<li href>` with no type error.
        // oxlint-disable-next-line react/jsx-props-no-spreading
        {...props}
        component="a"
        // Space is the half of the menu pattern the anchor doesn't cover: a
        // native `<a>` activates on Enter only, and MUI drops its synthetic
        // Space -> click once the root is an `<a href>`
        // (`useButtonBase.hasNativeKeyboardActivation`).
        onKeyDown={(event) => {
            props.onKeyDown?.(event);
            if (event.key === " " && event.target === event.currentTarget) {
                event.preventDefault(); // Don't scroll the page
            }
        }}
        onKeyUp={(event) => {
            props.onKeyUp?.(event);
            if (
                event.key === " " &&
                event.target === event.currentTarget &&
                !event.defaultPrevented
            ) {
                event.currentTarget.click();
            }
        }}
    />
);

const RouterLinkMenuItem = createLink(AnchorMenuItem);

const APP_BAR_HEIGHT_PX = "64px";

// The drawer's footer pair. The toolbar menu links the same two pages as real
// menu items instead — see the note there.
const LegalLinks = () => {
    return (
        <Stack
            direction="row"
            sx={{
                gap: 1,
                alignItems: "center",
            }}
        >
            <Link to="/terms">
                <Typography variant="caption" color="textSecondary">
                    Terms
                </Typography>
            </Link>
            <Typography variant="caption" color="textSecondary">
                ·
            </Typography>
            <Link to="/privacy">
                <Typography variant="caption" color="textSecondary">
                    Privacy
                </Typography>
            </Link>
        </Stack>
    );
};

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

    // oxlint-disable-next-line unicorn/prefer-at
    const currentMatch = routerState.matches[routerState.matches.length - 1];

    switch (currentMatch.routeId) {
        case "/session/$uuid":
        case "/session/$uuid_/detail":
        case "/wrapped/$uuid": {
            return currentMatch.params.uuid;
        }
        case "/history/explore": {
            const { uuids } = currentMatch.search;
            return uuids.length > 0 ? uuids[0] : null;
        }
        case "__root__":
        case "/":
        case "/about":
        case "/downloads":
        case "/privacy":
        case "/settings":
        case "/terms":
        case "/session/":
        case "/wrapped/": {
            return null;
        }
        default: {
            currentMatch satisfies never;
            return null;
        } // Unreachable
    }
}

export const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
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
                    borderBottom: "1px solid",
                    borderColor: "divider",
                    height: APP_BAR_HEIGHT_PX,
                }}
            >
                <Toolbar variant="regular">
                    <Stack
                        direction="row"
                        spacing={2}
                        sx={{
                            alignItems: "center",
                            justifyContent: "space-between",
                            width: "100%",
                        }}
                    >
                        <Link to="/" style={{ textDecoration: "none" }}>
                            <Stack
                                direction="row"
                                sx={{
                                    gap: 1,
                                    alignItems: "center",
                                }}
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
                        <Stack
                            direction="row"
                            sx={{
                                gap: 1,
                            }}
                        >
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
                            {playerToNavigate !== null ? (
                                <RouterLinkMenuItem
                                    to="/session/$uuid"
                                    selected={location.pathname.startsWith("/session")}
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
                                </RouterLinkMenuItem>
                            ) : (
                                <RouterLinkMenuItem
                                    to="/session"
                                    selected={location.pathname.startsWith("/session")}
                                    onClick={handleCloseMenu}
                                >
                                    <ListItemIcon>
                                        <TrendingUp />
                                    </ListItemIcon>
                                    <ListItemText primary="Session stats" />
                                </RouterLinkMenuItem>
                            )}
                            <RouterLinkMenuItem
                                to="/history/explore"
                                selected={location.pathname === "/history/explore"}
                                search={{
                                    uuids:
                                        playerToNavigate !== null
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
                            </RouterLinkMenuItem>
                            {playerToNavigate !== null ? (
                                <RouterLinkMenuItem
                                    to="/wrapped/$uuid"
                                    selected={location.pathname.startsWith("/wrapped")}
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
                                </RouterLinkMenuItem>
                            ) : (
                                <RouterLinkMenuItem
                                    to="/wrapped"
                                    selected={location.pathname.startsWith("/wrapped")}
                                    onClick={handleCloseMenu}
                                >
                                    <ListItemIcon>
                                        <Redeem />
                                    </ListItemIcon>
                                    <ListItemText
                                        primary={`Wrapped ${getWrappedYear().toString()}`}
                                    />
                                </RouterLinkMenuItem>
                            )}
                            <RouterLinkMenuItem
                                selected={location.pathname === "/downloads"}
                                to="/downloads"
                                onClick={handleCloseMenu}
                            >
                                <ListItemIcon>
                                    <Download />
                                </ListItemIcon>
                                <ListItemText primary="Downloads" />
                            </RouterLinkMenuItem>
                            <RouterLinkMenuItem
                                selected={location.pathname === "/settings"}
                                to="/settings"
                                onClick={handleCloseMenu}
                            >
                                <ListItemIcon>
                                    <Settings />
                                </ListItemIcon>
                                <ListItemText primary="Settings" />
                            </RouterLinkMenuItem>
                            <RouterLinkMenuItem
                                selected={location.pathname === "/about"}
                                to="/about"
                                onClick={handleCloseMenu}
                            >
                                <ListItemIcon>
                                    <Info />
                                </ListItemIcon>
                                <ListItemText primary="About" />
                            </RouterLinkMenuItem>
                            <Divider />
                            {/* Real menu items, not the compact `LegalLinks`
                              pair the drawer uses: `Menu` swallows Tab and
                              `MenuList` skips children without a tabindex, so
                              anything else here is unreachable by keyboard —
                              and below `lg` this menu is the only route to
                              these two pages. */}
                            <RouterLinkMenuItem
                                selected={location.pathname === "/terms"}
                                to="/terms"
                                onClick={handleCloseMenu}
                            >
                                <ListItemIcon>
                                    <Gavel />
                                </ListItemIcon>
                                <ListItemText primary="Terms" />
                            </RouterLinkMenuItem>
                            <RouterLinkMenuItem
                                selected={location.pathname === "/privacy"}
                                to="/privacy"
                                onClick={handleCloseMenu}
                            >
                                <ListItemIcon>
                                    <PrivacyTip />
                                </ListItemIcon>
                                <ListItemText primary="Privacy" />
                            </RouterLinkMenuItem>
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
                        width: 240,
                        boxSizing: "border-box",
                    },
                }}
            >
                <Link to="/" style={{ textDecoration: "none" }}>
                    <Stack
                        direction="row"
                        sx={{
                            paddingY: 1.5,
                            paddingX: 3,
                            gap: 1,
                            alignItems: "center",
                        }}
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
                <Stack
                    sx={{
                        height: "100%",
                        overflow: "auto",
                    }}
                >
                    <List dense component="menu">
                        <ListItem disablePadding>
                            {playerToNavigate !== null ? (
                                <RouterLinkItemButton
                                    selected={location.pathname.startsWith("/session")}
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
                                    selected={location.pathname.startsWith("/session")}
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
                                selected={location.pathname === "/history/explore"}
                                to="/history/explore"
                                search={{
                                    uuids:
                                        playerToNavigate !== null
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
                            {playerToNavigate !== null ? (
                                <RouterLinkItemButton
                                    selected={location.pathname.startsWith("/wrapped")}
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
                                    selected={location.pathname.startsWith("/wrapped")}
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
                <Stack
                    sx={{
                        padding: 1,
                        gap: 1,
                        justifyContent: "center",
                        alignItems: "center",
                    }}
                >
                    <DarkModeSwitch />
                    <LegalLinks />
                </Stack>
            </Drawer>
            <Stack
                component="main"
                sx={{
                    padding: 1,
                    marginTop: { xs: APP_BAR_HEIGHT_PX, lg: 0 },
                    width: "100%",
                    height: "100%",
                    // `<main>` is a flex item next to the permanent drawer, so
                    // its default `min-width: auto` floors it at the content's
                    // min-content width. Wide content (e.g. the session
                    // detail game strip) then refuses to give up room for the
                    // 240px drawer and the whole page scrolls sideways instead
                    // of the content scrolling inside its own container.
                    minWidth: 0,
                }}
            >
                {/* Wrap the children in a padded box so the bottom spacer
                  scrolls with the content — padding on `<main>` itself doesn't,
                  since it's overflow:visible and ends up flush with the
                  viewport. `flexGrow` + flex column lets the wrapper fill
                  `<main>` when content is short (so routes that center on
                  `height:100%`, e.g. the home page, keep a full-height
                  containing block) and grow past the viewport when content is
                  long (so the spacer trails the content). Don't add
                  `minHeight: 0` here: it clamps the wrapper to the viewport,
                  burying the spacer mid-content on pages that overflow. */}
                <Box
                    sx={{
                        flexGrow: 1,
                        display: "flex",
                        flexDirection: "column",
                        paddingBottom: 6,
                    }}
                >
                    {children}
                </Box>
            </Stack>
        </Box>
    );
};
