import { type History } from "#queries/history.ts";
import { type PlayerDataPIT } from "#queries/playerdata.ts";
import { type GamemodeKey, type StatKey, type VariantKey } from "./keys.ts";
import { bedwarsLevelFromExp } from "./stars.ts";

export function getStat(
    playerData: PlayerDataPIT,
    gamemode: GamemodeKey,
    stat: Exclude<StatKey, "winstreak">,
): number;
export function getStat(
    playerData: PlayerDataPIT,
    gamemode: GamemodeKey,
    stat: StatKey,
): number | null;
export function getStat(
    playerData: PlayerDataPIT,
    gamemode: GamemodeKey,
    stat: StatKey,
): number | null {
    const selectedGamemode = playerData[gamemode];

    switch (stat) {
        case "experience":
            return playerData.experience;
        case "winstreak":
            return selectedGamemode.winstreak;
        case "stars":
            return bedwarsLevelFromExp(playerData.experience);
        case "fkdr": {
            const finalKills = selectedGamemode.finalKills;
            const finalDeaths = selectedGamemode.finalDeaths;
            if (finalDeaths === 0) {
                return finalKills;
            } else {
                return finalKills / finalDeaths;
            }
        }
        case "kdr": {
            const kills = selectedGamemode.kills;
            const deaths = selectedGamemode.deaths;
            if (deaths === 0) {
                return kills;
            } else {
                return kills / deaths;
            }
        }
        case "index": {
            const fkdr = getStat(playerData, gamemode, "fkdr");
            const stars = getStat(playerData, gamemode, "stars");
            return fkdr ** 2 * stars;
        }
        default:
            // I believe all stats default to 0 if they are not present
            return playerData[gamemode][stat];
    }
}

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

export function computeStat(
    playerData: PlayerDataPIT,
    gamemode: GamemodeKey,
    stat: Exclude<StatKey, "winstreak">,
    variant: VariantKey,
    history: History,
): number;
export function computeStat(
    playerData: PlayerDataPIT,
    gamemode: GamemodeKey,
    stat: StatKey,
    variant: VariantKey,
    history: History,
): number | null;
export function computeStat(
    playerData: PlayerDataPIT,
    gamemode: GamemodeKey,
    stat: StatKey,
    variant: VariantKey,
    history: History,
): number | null {
    if (variant === "overall") {
        return getStat(playerData, gamemode, stat);
    }

    switch (stat) {
        case "fkdr": {
            const finalKills = computeStat(
                playerData,
                gamemode,
                "finalKills",
                variant,
                history,
            );

            const finalDeaths = computeStat(
                playerData,
                gamemode,
                "finalDeaths",
                variant,
                history,
            );

            if (finalDeaths === 0) {
                return finalKills;
            } else {
                return finalKills / finalDeaths;
            }
        }
        case "kdr": {
            const kills = computeStat(
                playerData,
                gamemode,
                "kills",
                variant,
                history,
            );
            const deaths = computeStat(
                playerData,
                gamemode,
                "deaths",
                variant,
                history,
            );

            if (deaths === 0) {
                return kills;
            } else {
                return kills / deaths;
            }
        }
        case "index": {
            const fkdr = computeStat(
                playerData,
                gamemode,
                "fkdr",
                variant,
                history,
            );
            const stars = computeStat(
                playerData,
                gamemode,
                "stars",
                variant,
                history,
            );
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
}
