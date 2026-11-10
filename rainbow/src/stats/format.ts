import type { StatKey } from "./keys.ts";

export type StatFormatKind = "integer" | "decimal" | "percentage";

// Record<StatKey, …> is exhaustive: a new stat won't compile until its format
// kind is declared here. (Commit 3 adds "percentage" and the `winrate` entry.)
export const STAT_FORMAT_KIND: Record<StatKey, StatFormatKind> = {
    experience: "integer",
    stars: "decimal",
    winstreak: "integer",
    gamesPlayed: "integer",
    wins: "integer",
    losses: "integer",
    bedsBroken: "integer",
    bedsLost: "integer",
    finalKills: "integer",
    finalDeaths: "integer",
    kills: "integer",
    deaths: "integer",
    fkdr: "decimal",
    kdr: "decimal",
    bblr: "decimal",
    wlr: "decimal",
    winrate: "percentage",
    index: "integer",
};

export const getStatFormatKind = (stat: StatKey): StatFormatKind =>
    STAT_FORMAT_KIND[stat];

// Stats where a rising value is "bad" (i.e. rendered in error colours): more
// deaths, more losses, etc. Every other stat improves as it grows.
export const BAD_STATS: readonly StatKey[] = [
    "deaths",
    "finalDeaths",
    "bedsLost",
    "losses",
];

export const isBadStat = (stat: StatKey): boolean => BAD_STATS.includes(stat);

export type TrendDirection = "up" | "down" | "flat";

// Three-way comparison of a stat's movement from `from` to `to`.
export const getTrendDirection = (from: number, to: number): TrendDirection => {
    if (to > from) {
        return "up";
    }
    if (to < from) {
        return "down";
    }
    return "flat";
};

export type TrendSentiment = "good" | "bad" | "neutral";

// Whether moving in `direction` is good or bad for `stat`. A rising bad stat (or
// a falling good stat) is "bad"; the opposite is "good"; no movement is neutral.
export const getTrendSentiment = (
    stat: StatKey,
    direction: TrendDirection,
): TrendSentiment => {
    if (direction === "flat") {
        return "neutral";
    }
    return (direction === "up") === isBadStat(stat) ? "bad" : "good";
};

interface FormatStatValueOptions {
    // "compact" → cards / diffs / short contexts (fewer decimals);
    // "detailed" → values / tooltips / hover detail (more decimals).
    readonly precision?: "compact" | "detailed";
    readonly signDisplay?: Intl.NumberFormatOptions["signDisplay"];
}

export const formatStatValue = (
    stat: StatKey,
    value: number,
    { precision = "compact", signDisplay }: FormatStatValueOptions = {},
): string => {
    switch (getStatFormatKind(stat)) {
        case "decimal": {
            const digits = precision === "detailed" ? 3 : 2;
            return value.toLocaleString(undefined, {
                minimumFractionDigits: digits,
                maximumFractionDigits: digits,
                signDisplay,
            });
        }
        case "integer": {
            return value.toLocaleString(undefined, {
                maximumFractionDigits: 0,
                signDisplay,
            });
        }
        case "percentage": {
            // `style: "percent"` scales by 100 and appends a locale-aware percent
            // sign/spacing, so pass the raw fraction (not `value * 100`).
            // min = max (like the decimal case) for a fixed number of decimals.
            const digits = precision === "detailed" ? 2 : 1;
            return value.toLocaleString(undefined, {
                style: "percent",
                minimumFractionDigits: digits,
                maximumFractionDigits: digits,
                signDisplay,
            });
        }
    }
};
