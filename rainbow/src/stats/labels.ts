import { GamemodeKey, StatKey, VariantKey } from "./keys.ts";

export const getFullStatLabel = (stat: StatKey, capitalize = false): string => {
    switch (stat) {
        case "experience":
            return capitalize ? "Experience" : "experience";
        case "stars":
            return capitalize ? "Stars" : "stars";
        case "kills":
            return capitalize ? "Kills" : "kills";
        case "deaths":
            return capitalize ? "Deaths" : "deaths";
        case "finalKills":
            return capitalize ? "Final kills" : "final kills";
        case "finalDeaths":
            return capitalize ? "Final deaths" : "final deaths";
        case "bedsBroken":
            return capitalize ? "Beds broken" : "beds broken";
        case "bedsLost":
            return capitalize ? "Beds lost" : "beds lost";
        case "winstreak":
            return capitalize ? "Winstreak" : "winstreak";
        case "wins":
            return capitalize ? "Wins" : "wins";
        case "losses":
            return capitalize ? "Losses" : "losses";
        case "gamesPlayed":
            return capitalize ? "Games played" : "games played";
        case "kdr":
            return capitalize ? "Kill/death ratio" : "kill/death ratio";
        case "fkdr":
            return capitalize
                ? "Final kill/death ratio"
                : "final kill/death ratio";
        case "index":
            return capitalize
                ? "Index (FKDR^2 * Stars)"
                : "index (FKDR^2 * stars)";
    }
};

export const getShortStatLabel = (
    stat: StatKey,
    capitalize = false,
): string => {
    switch (stat) {
        case "experience":
            return capitalize ? "EXP" : "EXP";
        case "stars":
            return capitalize ? "Stars" : "stars";
        case "kills":
            return capitalize ? "Kills" : "kills";
        case "deaths":
            return capitalize ? "Deaths" : "deaths";
        case "finalKills":
            return capitalize ? "Finals" : "finals";
        case "finalDeaths":
            return capitalize ? "Final deaths" : "final deaths";
        case "bedsBroken":
            return capitalize ? "Beds" : "beds";
        case "bedsLost":
            return capitalize ? "Beds lost" : "beds lost";
        case "winstreak":
            return capitalize ? "WS" : "WS";
        case "wins":
            return capitalize ? "Wins" : "wins";
        case "losses":
            return capitalize ? "Losses" : "losses";
        case "gamesPlayed":
            return capitalize ? "Games" : "games";
        case "kdr":
            return capitalize ? "KDR" : "KDR";
        case "fkdr":
            return capitalize ? "FKDR" : "FKDR";
        case "index":
            return capitalize ? "Index" : "index";
    }
};

export const getGamemodeLabel = (
    gamemode: GamemodeKey,
    capitalize = false,
): string => {
    switch (gamemode) {
        case "overall":
            return capitalize ? "Total" : "total";
        case "solo":
            return capitalize ? "Solo" : "solo";
        case "doubles":
            return capitalize ? "Doubles" : "doubles";
        case "threes":
            return capitalize ? "Threes" : "threes";
        case "fours":
            return capitalize ? "Fours" : "fours";
    }
};

export const getVariantLabel = (
    variant: VariantKey,
    capitalize = false,
): string => {
    switch (variant) {
        case "session":
            // TODO: Show daily/weekly/etc?
            return capitalize ? "Session" : "session";
        case "overall":
            return capitalize ? "All time" : "all time";
    }
};
