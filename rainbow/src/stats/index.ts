import { History, PlayerDataPIT } from "@/queries/history";
import { GamemodeKey, StatKey, VariantKey } from "./keys";
import { bedwarsLevelFromExp } from "./stars";

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

export const computeStat = (
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
