// The Prism Overlay MUI theme.
//
// Light and dark are defined as MUI `colorSchemes`, so `useColorScheme()`
// (see DarkModeSwitch) toggles between them and "system" follows the OS.
//
// On top of MUI's standard palette we encode a few design tokens that have no
// built-in home — `surface2`, `borderHi`, `headerBg` — plus the identity colour
// maps the product needs: `gamemode` (keyed off GamemodeKey, so adding a
// gamemode is a type error until it has a colour) and `rainbow` (the general
// accent set used for stat cards and chart strokes). Both live in the palette
// so they can diverge per scheme if we ever want different light/dark values.
//
// NB: CSS theme variables (`cssVariables: true`) are intentionally *not* enabled
// — recharts feeds `theme.palette.*` values straight into SVG presentation
// attributes, which don't resolve `var(--...)`. Keeping plain colour strings
// avoids breaking the charts.

import { createTheme } from "@mui/material/styles";
import type { PaletteOptions, Theme, ThemeOptions } from "@mui/material/styles";
// Registers the MUI X picker components (MuiPickersOutlinedInput, ...) on the
// theme's `components` type so we can style them below. The empty type import
// is the canonical way to load this types-only augmentation module.
// oxlint-disable-next-line import/no-empty-named-blocks, unicorn/require-module-specifiers
import type {} from "@mui/x-date-pickers/themeAugmentation";

import type { GamemodeKey } from "#stats/keys.ts";

import {
    DARK_TOKENS,
    GAMEMODE_COLORS,
    LIGHT_TOKENS,
    RAINBOW_COLORS,
} from "./tokens.ts";
import type { SchemeTokens } from "./tokens.ts";

declare module "@mui/material/styles" {
    interface Palette {
        /** Inset surface for mini-cards, zebra rows, kbd hints. */
        surface2: string;
        /** Stronger border for hover / active controls. */
        borderHi: string;
        /** App bar / drawer background. */
        headerBg: string;
        /** Muted, least-prominent accent for footers, chart future-markers and
         * scrollbars. Deliberately separate from MUI's `text.disabled` so the
         * two can be tuned independently. */
        textMuted: string;
        /** Per-gamemode identity accent colours. */
        gamemode: Record<GamemodeKey, string>;
        /** Brand rainbow, ordered red → violet. Used as the general accent set
         * (Wrapped cards, chart strokes). May differ per scheme. Readonly: it's
         * a shared theme array, so consumers must not mutate it. */
        rainbow: readonly string[];
    }
    interface PaletteOptions {
        surface2?: string;
        borderHi?: string;
        headerBg?: string;
        textMuted?: string;
        gamemode?: Record<GamemodeKey, string>;
        rainbow?: readonly string[];
    }
    interface TypographyVariants {
        /** Monospace family for tabular numbers / stat values. */
        fontFamilyMonospace: string;
    }
    interface TypographyVariantsOptions {
        fontFamilyMonospace?: string;
    }
}

const FONT_FAMILY_MONOSPACE =
    '"Roboto Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';

const buildPalette = (
    tokens: Readonly<SchemeTokens>,
    mode: "light" | "dark",
): PaletteOptions => ({
    mode,
    primary: { main: tokens.primary, light: tokens.primaryHi },
    secondary: { main: tokens.secondary },
    success: { main: tokens.win },
    error: { main: tokens.loss },
    warning: { main: tokens.warn },
    info: { main: tokens.info },
    background: { default: tokens.bg, paper: tokens.surface },
    // text.disabled is intentionally left to MUI's default so disabled-control
    // styling can be tuned without touching muted text / chart markers (see
    // palette.textMuted below).
    text: {
        primary: tokens.text,
        secondary: tokens.textDim,
    },
    divider: tokens.border,
    surface2: tokens.surface2,
    borderHi: tokens.borderHi,
    headerBg: tokens.headerBg,
    textMuted: tokens.textMuted,
    // "overall" tracks the scheme's primary colour so the aggregate series is
    // the same blue everywhere (session sparkline and explore chart alike).
    gamemode: { ...GAMEMODE_COLORS, overall: tokens.primary },
    rainbow: [...RAINBOW_COLORS],
});

const sharedOptions: ThemeOptions = {
    shape: { borderRadius: 8 },
    typography: { fontFamilyMonospace: FONT_FAMILY_MONOSPACE },
    components: {
        MuiCssBaseline: {
            styleOverrides: (theme) => ({
                // Firefox
                "*": {
                    scrollbarWidth: "thin",
                    scrollbarColor: `${theme.palette.borderHi} transparent`,
                },
                // WebKit / Blink
                "*::-webkit-scrollbar": { width: 10, height: 10 },
                "*::-webkit-scrollbar-track": { background: "transparent" },
                "*::-webkit-scrollbar-thumb": {
                    background: theme.palette.borderHi,
                    borderRadius: 5,
                },
                "*::-webkit-scrollbar-thumb:hover": {
                    background: theme.palette.textMuted,
                },
            }),
        },
        // Flat surfaces — drop MUI's dark-mode elevation gradient so cards read
        // as the design's solid panels.
        MuiPaper: {
            styleOverrides: { root: { backgroundImage: "none" } },
        },
        // Cards use the design's softer 12px corner regardless of the smaller
        // base radius used by buttons/inputs.
        MuiCard: {
            styleOverrides: { root: { borderRadius: 12 } },
        },
        // Outlined controls are transparent by default, so on the slightly-grey
        // page background they blend in. Fill them with the surface colour so
        // every form control reads as raised the way the design intends — no
        // per-usage styling needed. MUI X date pickers use their own input
        // component (PickersOutlinedInput), and outlined buttons (e.g. the
        // "Current interval" trigger) need the same treatment.
        MuiOutlinedInput: {
            styleOverrides: {
                root: ({ theme }) => ({
                    backgroundColor: theme.palette.background.paper,
                }),
            },
        },
        MuiPickersOutlinedInput: {
            styleOverrides: {
                root: ({ theme }) => ({
                    backgroundColor: theme.palette.background.paper,
                }),
            },
        },
        MuiButton: {
            styleOverrides: {
                outlined: ({ theme }) => ({
                    backgroundColor: theme.palette.background.paper,
                }),
            },
        },
        // Outlined chips (e.g. the history-explorer quick time-range filters)
        // are transparent too — give them the surface colour so they read as
        // controls on the page rather than blending in.
        MuiChip: {
            styleOverrides: {
                outlined: ({ theme }) => ({
                    backgroundColor: theme.palette.background.paper,
                }),
            },
        },
        // The app bar and the permanent navigation drawer use the dedicated
        // header surface in both schemes (default AppBar colour would be the
        // primary blue), so consumers don't have to set it.
        MuiAppBar: {
            defaultProps: { color: "default", elevation: 0 },
            styleOverrides: {
                colorDefault: ({ theme }) => ({
                    backgroundColor: theme.palette.headerBg,
                }),
            },
        },
        MuiDrawer: {
            styleOverrides: {
                paper: ({ theme }) => ({
                    backgroundColor: theme.palette.headerBg,
                }),
            },
        },
    },
};

export const theme = createTheme({
    colorSchemes: {
        light: { palette: buildPalette(LIGHT_TOKENS, "light") },
        dark: { palette: buildPalette(DARK_TOKENS, "dark") },
    },
    ...sharedOptions,
});

/**
 * A standalone dark theme used for the Wrapped image export. The export is
 * rendered off-screen by html-to-image and must look identical regardless of
 * the user's current colour scheme, so it pins the dark palette and collapses
 * all breakpoints. It still carries the custom tokens (gamemode/stat/rainbow),
 * unlike a bare `createTheme({ palette: { mode: "dark" } })`.
 */
export const createExportTheme = (): Theme =>
    createTheme({
        ...sharedOptions,
        palette: buildPalette(DARK_TOKENS, "dark"),
        breakpoints: {
            values: { xs: 0, sm: 0, md: 0, lg: 0, xl: 1 },
        },
    });
