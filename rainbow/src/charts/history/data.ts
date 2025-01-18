import { History, PlayerDataPIT } from "@/queries/history";
import {
    ALL_GAMEMODE_KEYS,
    ALL_STAT_KEYS,
    ALL_VARIANT_KEYS,
    GamemodeKey,
    StatKey,
    VariantKey,
} from "./types";
import { DataKey, makeDataKey } from "./dataKeys";

type ChartDataEntry = Record<DataKey, number | undefined | null> & {
    queriedAt: number;
};

export type ChartData = ChartDataEntry[];

// Amount of levels to prestige
const LEVELS_PER_PRESTIGE = 100;

// The exp required to level up once
const LEVEL_COST = 5000;

// The exp required to level up to the first few levels after a prestige
const EASY_LEVEL_COSTS = { 1: 500, 2: 1000, 3: 2000, 4: 3500 };

// The exp required to level up past the easy levels
const EASY_EXP = Object.values(EASY_LEVEL_COSTS).reduce(
    (acc, cost) => acc + cost,
    0,
);

// The amount of easy levels
const EASY_LEVELS = Object.keys(EASY_LEVEL_COSTS).length;

// The exp required to prestige
const PRESTIGE_EXP = EASY_EXP + (100 - EASY_LEVELS) * LEVEL_COST;

/*
 * Return the bedwars level corresponding to the given experience
 *
 * The fractional part represents the progress towards the next level
 *
 * NOTE: Translated from the python implementation in Prism
 */
export const bedwarsLevelFromExp = (exp: number): number => {
    let levels = Math.floor(exp / PRESTIGE_EXP) * LEVELS_PER_PRESTIGE;
    exp %= PRESTIGE_EXP;

    // The first few levels have different costs
    for (let i = 1; i <= EASY_LEVELS; i++) {
        const cost = EASY_LEVEL_COSTS[i as keyof typeof EASY_LEVEL_COSTS];
        if (exp >= cost) {
            levels += 1;
            exp -= cost;
        } else {
            // We can't afford the next level, so we have found the level we are at
            break;
        }
    }
    levels += Math.floor(exp / LEVEL_COST);
    exp %= LEVEL_COST;

    const nextLevel = (levels + 1) % LEVELS_PER_PRESTIGE;

    // The cost of the next level, fallback to LEVEL_COST if it is not an easy level
    let nextLevelCost = LEVEL_COST;
    if (nextLevel in EASY_LEVEL_COSTS) {
        nextLevelCost =
            EASY_LEVEL_COSTS[nextLevel as keyof typeof EASY_LEVEL_COSTS];
    }

    return levels + exp / nextLevelCost;
};

// Stats that may be hidden from the API
const CONCEALABLE_STATS = ["winstreak"];

const getStat = (
    playerData: PlayerDataPIT,
    gamemode: GamemodeKey,
    stat: StatKey,
): number | null => {
    const selectedGamemode = playerData[gamemode];

    switch (stat) {
        case "experience":
            return playerData.experience ?? 0;
        case "stars":
            return bedwarsLevelFromExp(playerData.experience ?? 0);
        case "fkdr": {
            const finalKills = selectedGamemode.finalKills ?? 0;
            const finalDeaths = selectedGamemode.finalDeaths ?? 0;
            if (finalDeaths === 0) {
                return finalKills;
            } else {
                return finalKills / finalDeaths;
            }
        }
        case "kdr": {
            const kills = selectedGamemode.kills ?? 0;
            const deaths = selectedGamemode.deaths ?? 0;
            if (deaths === 0) {
                return kills;
            } else {
                return kills / deaths;
            }
        }
        case "index": {
            const fkdr = getStat(playerData, gamemode, "fkdr") ?? 0;
            const stars = getStat(playerData, gamemode, "stars") ?? 0;
            return fkdr ** 2 * stars;
        }
        default:
            if (CONCEALABLE_STATS.includes(stat)) {
                return playerData[gamemode][stat];
            }
            // I believe all stats default to 0 if they are not present
            return playerData[gamemode][stat] ?? 0;
    }
};

const findBaseline = (
    history: History,
    gamemode: GamemodeKey,
    stat: StatKey,
): number | null => {
    for (const playerData of history) {
        const value = getStat(playerData, gamemode, stat);
        if (value !== null) {
            return value;
        }
    }
    return null;
};

const computeStat = (
    playerData: PlayerDataPIT,
    gamemode: GamemodeKey,
    stat: StatKey,
    variant: VariantKey,
    history: History,
): number | null => {
    if (variant === "overall") {
        return getStat(playerData, gamemode, stat);
    }

    switch (stat) {
        case "fkdr": {
            const finalKills =
                computeStat(
                    playerData,
                    gamemode,
                    "finalKills",
                    variant,
                    history,
                ) ?? 0;

            const finalDeaths =
                computeStat(
                    playerData,
                    gamemode,
                    "finalDeaths",
                    variant,
                    history,
                ) ?? 0;

            if (finalDeaths === 0) {
                return finalKills;
            } else {
                return finalKills / finalDeaths;
            }
        }
        case "kdr": {
            const kills =
                computeStat(playerData, gamemode, "kills", variant, history) ??
                0;
            const deaths =
                computeStat(playerData, gamemode, "deaths", variant, history) ??
                0;

            if (deaths === 0) {
                return kills;
            } else {
                return kills / deaths;
            }
        }
        case "index": {
            const fkdr =
                computeStat(playerData, gamemode, "fkdr", variant, history) ??
                0;
            const stars =
                computeStat(playerData, gamemode, "stars", variant, history) ??
                0;
            return fkdr ** 2 * stars;
        }
        default: {
            const baseline = findBaseline(history, gamemode, stat);
            const value = getStat(playerData, gamemode, stat);
            if (baseline === null || value === null) {
                return null;
            }
            return value - baseline;
        }
    }
};

const generateChartDataFromSingleHistory = (history: History): ChartData => {
    const data: ChartData = [];
    for (const playerData of history) {
        const entry: ChartDataEntry = {
            queriedAt: playerData.queriedAt.getTime(),
        };
        for (const variant of ALL_VARIANT_KEYS) {
            for (const gamemode of ALL_GAMEMODE_KEYS) {
                for (const stat of ALL_STAT_KEYS) {
                    const key = makeDataKey({
                        uuid: playerData.uuid,
                        stat,
                        variant,
                        gamemode,
                    });

                    entry[key] = computeStat(
                        playerData,
                        gamemode,
                        stat,
                        variant,
                        history,
                    );
                }
            }
        }
        data.push(entry);
    }
    return data;
};

export const clusterChartData = (chartData: ChartData): ChartData => {
    if (chartData.length === 0) {
        return [];
    }

    const timeSpan =
        chartData[chartData.length - 1].queriedAt - chartData[0].queriedAt;
    // Cluster entries that are closer than 1% of the time span or 1 minute
    const threshold = Math.max(timeSpan / 100, 1000 * 60);

    const clusteredChartData: ChartData = [];
    for (let i = chartData.length - 1; i >= 0; i--) {
        const entry = chartData[i];
        let entriesToCluster = 1; // Number of entries to cluster, including this one
        while (
            i - entriesToCluster >= 0 &&
            entry.queriedAt - chartData[i - entriesToCluster].queriedAt <=
                threshold
        ) {
            entriesToCluster++;
        }
        for (let offset = 0; offset < entriesToCluster; offset++) {
            const newEntry = {
                ...chartData[i - offset],
                queriedAt: entry.queriedAt,
            };
            clusteredChartData.push(newEntry);
        }
        // Skip the entries that were clustered, the current entry is already skipped by the for loop
        i -= entriesToCluster - 1;
    }

    return clusteredChartData.reverse();
};

export const generateChartData = (histories: History[]): ChartData => {
    const chartData = histories
        .flatMap(generateChartDataFromSingleHistory)
        .sort((a, b) => a.queriedAt - b.queriedAt);

    if (chartData.length === 0) {
        return [];
    }

    const clusteredChartData = clusterChartData(chartData);

    // Merge duplicate queriedAt values
    const mergedChartData: ChartData = [clusteredChartData[0]];
    for (const entry of clusteredChartData) {
        const lastEntry = mergedChartData[mergedChartData.length - 1];
        if (lastEntry.queriedAt === entry.queriedAt) {
            mergedChartData[mergedChartData.length - 1] = {
                ...lastEntry,
                ...entry,
            };
        } else {
            mergedChartData.push(entry);
        }
    }
    return mergedChartData;
};
