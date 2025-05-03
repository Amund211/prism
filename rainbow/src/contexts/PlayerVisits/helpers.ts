import { isNormalizedUUID } from "#helpers/uuid.ts";
import { useLocalStorage } from "#hooks/useLocalStorage.ts";

const localStorageKey = "playerVisits";

const loadedAt = new Date();

interface PlayerInfo {
    visitedCount: number;
    lastVisited: Date;
}

type PlayerVisits = Record<string, PlayerInfo | undefined>;

const parseStoredInfo = (stored: string | null): PlayerVisits => {
    if (stored === null) {
        return {};
    }

    let rawParsed: unknown;
    try {
        rawParsed = JSON.parse(stored);
    } catch {
        return {};
    }

    if (typeof rawParsed !== "object" || rawParsed === null) {
        return {};
    }

    const storedInfo: PlayerVisits = {};
    for (const uuid in rawParsed) {
        if (!isNormalizedUUID(uuid)) {
            continue;
        }

        const value = (rawParsed as Record<string, unknown>)[uuid];
        if (typeof value !== "object" || value === null) {
            continue;
        }

        if (
            !("lastVisited" in value) ||
            typeof value.lastVisited !== "string"
        ) {
            continue;
        }
        const lastVisited = new Date(value.lastVisited);
        if (isNaN(lastVisited.getTime())) {
            continue;
        }

        if (
            !("visitedCount" in value) ||
            typeof value.visitedCount !== "number"
        ) {
            continue;
        }

        storedInfo[uuid] = { lastVisited, visitedCount: value.visitedCount };
    }

    return storedInfo;
};

const lastVisitedWeight = (lastVisited: Date): number => {
    const diff = loadedAt.getTime() - lastVisited.getTime();
    const days = diff / (1000 * 60 * 60 * 24);

    // NOTE: Also includes days < 0 for when the user has visited a player after the page was loaded
    if (days < 1) {
        return 4;
    }
    if (days < 7) {
        return 2;
    }
    if (days < 30) {
        return 1;
    }
    return 0.5;
};

const computeScore = (info: PlayerInfo): number => {
    return info.visitedCount * lastVisitedWeight(info.lastVisited);
};

export const orderPlayers = (players: PlayerVisits): string[] => {
    return Object.entries(players)
        .map(([uuid, info]) => {
            if (info === undefined) {
                return null;
            }
            return [uuid, info] as const;
        })
        .filter((entry) => entry !== null)
        .sort((a, b) => {
            return computeScore(b[1]) - computeScore(a[1]);
        })
        .map(([uuid]) => uuid);
};

export const removePlayerVisits = (visits: PlayerVisits, uuid: string) => {
    if (!isNormalizedUUID(uuid)) {
        throw new Error(`UUID not normalized: ${uuid}`);
    }

    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const { [uuid]: _, ...newVisits } = visits;
    return newVisits;
};

export const visitPlayer = (visits: PlayerVisits, uuid: string) => {
    if (!isNormalizedUUID(uuid)) {
        throw new Error(`UUID not normalized: ${uuid}`);
    }

    const oldVisitedCount = visits[uuid]?.visitedCount ?? 0;
    return {
        ...visits,
        [uuid]: {
            visitedCount: oldVisitedCount + 1,
            lastVisited: new Date(),
        },
    };
};

export const persistPlayerVisits = (visits: PlayerVisits) => {
    localStorage.setItem(localStorageKey, JSON.stringify(visits));
};

export const usePersistedPlayerVisits = (): PlayerVisits => {
    const stored = useLocalStorage(localStorageKey);

    return parseStoredInfo(stored);
};
