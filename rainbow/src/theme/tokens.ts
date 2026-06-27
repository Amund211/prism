// Design tokens for the Prism Overlay redesign.
//
// These are the raw colour values that back the MUI theme. They are kept
// separate from `createTheme` so they can be referenced directly (e.g. when
// building gradients) and so the light/dark token sets sit side by side for
// easy comparison.
//
// Semantic tokens (text/surface/border/win/loss/...) differ per colour scheme.
// Identity tokens (gamemode/rainbow) are shared across schemes — they are used
// as vivid accents (dots, chips, chart strokes) that read on both backgrounds.

import type { GamemodeKey } from "#stats/keys.ts";

/** Per-scheme semantic tokens. */
export interface SchemeTokens {
    /** Page background (`palette.background.default`). */
    bg: string;
    /** Card / panel background (`palette.background.paper`). */
    surface: string;
    /** Inset surface for mini-cards, zebra rows, kbd (`palette.surface2`). */
    surface2: string;
    /** App bar / drawer background (`palette.headerBg`). */
    headerBg: string;
    /** Hairline border (`palette.divider`). */
    border: string;
    /** Stronger border for hover / active controls (`palette.borderHi`). */
    borderHi: string;
    /** Primary text (`palette.text.primary`). */
    text: string;
    /** Dimmed text (`palette.text.secondary`). */
    textDim: string;
    /** Muted, least-prominent accent (`palette.textMuted`). */
    textMuted: string;
    /** Brand primary (`palette.primary.main`). */
    primary: string;
    /** Brighter primary for hover/light token (`palette.primary.light`). */
    primaryHi: string;
    /** Positive / win (`palette.success.main`). */
    win: string;
    /** Negative / loss (`palette.error.main`). */
    loss: string;
    /** Warning (`palette.warning.main`). */
    warn: string;
    /** Informational accent (`palette.info.main`). */
    info: string;
    /** Brand secondary, the "stars" purple (`palette.secondary.main`). */
    secondary: string;
}

export const DARK_TOKENS: SchemeTokens = {
    bg: "#0f1115",
    surface: "#171a21",
    surface2: "#1d2129",
    headerBg: "#1a1d24",
    border: "#262b35",
    borderHi: "#384050",
    text: "#ffffff",
    textDim: "#9aa3b2",
    textMuted: "#6b7280",
    primary: "#64b5f6",
    primaryHi: "#90caf9",
    win: "#4ade80",
    loss: "#f87171",
    warn: "#fbbf24",
    info: "#22d3ee",
    secondary: "#c084fc",
};

export const LIGHT_TOKENS: SchemeTokens = {
    bg: "#f5f6f8",
    surface: "#ffffff",
    surface2: "#fbfbfc",
    headerBg: "#ffffff",
    border: "#e3e6eb",
    borderHi: "#cfd4dc",
    text: "#1a1d24",
    textDim: "#5b6473",
    textMuted: "#8a93a3",
    primary: "#1976d2",
    primaryHi: "#2196f3",
    win: "#16a34a",
    loss: "#dc2626",
    warn: "#d97706",
    info: "#0891b2",
    secondary: "#9333ea",
};

/**
 * Per-gamemode accent colours for the four real modes. Used for chart strokes
 * and legend dots so a gamemode keeps a stable identity colour across the app.
 * Shared across light and dark. "overall" is intentionally absent — it resolves
 * to the scheme's `primary` colour (added in the theme), so the aggregate
 * series matches the rest of the UI in both schemes.
 */
export const GAMEMODE_COLORS: Record<Exclude<GamemodeKey, "overall">, string> = {
    solo: "#a855f7",
    doubles: "#06b6d4",
    threes: "#22c55e",
    fours: "#f59e0b",
};

/**
 * The brand rainbow, ordered red → violet. Used for accent ribbons, the hero
 * gradient and celebratory flourishes (confetti, Wrapped header).
 */
export const RAINBOW_COLORS: readonly string[] = [
    "#ef4444",
    "#f59e0b",
    "#eab308",
    "#22c55e",
    "#06b6d4",
    "#6366f1",
    "#a855f7",
];

/**
 * Build a CSS `linear-gradient` from the brand rainbow.
 * @param angle gradient angle in degrees (default 90 = left→right).
 */
export const rainbowGradient = (angle = 90): string =>
    `linear-gradient(${angle.toString()}deg, ${RAINBOW_COLORS.join(", ")})`;
