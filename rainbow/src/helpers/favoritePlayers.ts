import { useLocalStorage } from "#hooks/useLocalStorage.ts";

const localStorageKey = "favoritePlayers";

const loadedAt = new Date();

interface PlayerInfo {
    visitedCount: number;
    lastVisited: Date;
}

const parseStoredInfo = (
    stored: string | null,
): Record<string, PlayerInfo | undefined> => {
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

    const storedInfo: Record<string, PlayerInfo | undefined> = {};
    for (const key in rawParsed) {
        const value = (rawParsed as Record<string, unknown>)[key];
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

        storedInfo[key] = { lastVisited, visitedCount: value.visitedCount };
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

const orderPlayers = (
    players: Record<string, PlayerInfo | undefined>,
): string[] => {
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

export const removeFavoritePlayer = (uuid: string) => {
    const stored = localStorage.getItem(localStorageKey);
    const storedInfo = parseStoredInfo(stored);
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const { [uuid]: _, ...newStoredInfo } = storedInfo;
    localStorage.setItem(localStorageKey, JSON.stringify(newStoredInfo));
};

export const visitPlayer = (uuid: string) => {
    const stored = localStorage.getItem(localStorageKey);
    const storedInfo = parseStoredInfo(stored);

    const now = new Date();
    const oldVisitedCount = storedInfo[uuid]?.visitedCount ?? 0;
    storedInfo[uuid] = {
        visitedCount: oldVisitedCount + 1,
        lastVisited: now,
    };

    localStorage.setItem(localStorageKey, JSON.stringify(storedInfo));
};

export const useFavoritePlayers = (amount?: number): string[] => {
    // TODO: Update state when writing to localStorage in this tab (make a context and use state like the current user provider)
    const stored = useLocalStorage(localStorageKey);

    const ordered = orderPlayers(parseStoredInfo(stored));

    if (amount === undefined) {
        return ordered;
    }

    return ordered.slice(0, amount);
};

export const useOrderUUIDsByScore = () => {
    const favoritePlayers = useFavoritePlayers();
    return (uuids: string[]): string[] => {
        return [...uuids].sort((a, b) => {
            const aIndex = favoritePlayers.indexOf(a);
            const bIndex = favoritePlayers.indexOf(b);
            if (aIndex === -1) return 1;
            if (bIndex === -1) return -1;
            return aIndex - bIndex;
        });
    };
};
