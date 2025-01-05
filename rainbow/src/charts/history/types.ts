export const OVERALL_STAT_KEYS = ["experience", "stars"] as const;
export type OverallStatKey = (typeof OVERALL_STAT_KEYS)[number];

export const GAMEMODE_STAT_KEYS = [
    "winstreak",
    "gamesPlayed",
    "wins",
    "losses",
    "bedsBroken",
    "bedsLost",
    "finalKills",
    "finalDeaths",
    "kills",
    "deaths",
    "fkdr",
    "kdr",
    "index",
] as const;
export type GamemodeStatKey = (typeof GAMEMODE_STAT_KEYS)[number];

export const ALL_STAT_KEYS = [
    ...OVERALL_STAT_KEYS,
    ...GAMEMODE_STAT_KEYS,
] as const;
export type StatKey = (typeof ALL_STAT_KEYS)[number];

export const ALL_GAMEMODE_KEYS = [
    "solo",
    "doubles",
    "threes",
    "fours",
    "overall",
] as const;
export type GamemodeKey = (typeof ALL_GAMEMODE_KEYS)[number];

export const ALL_VARIANT_KEYS = ["session", "overall"] as const;
export type VariantKey = (typeof ALL_VARIANT_KEYS)[number];
