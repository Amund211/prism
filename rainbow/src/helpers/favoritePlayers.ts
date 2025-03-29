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
    amount: number,
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
        .map(([uuid]) => uuid)
        .slice(0, amount);
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

export const getFavoritePlayers = (amount: number): string[] => {
    const stored = localStorage.getItem(localStorageKey);
    return orderPlayers(parseStoredInfo(stored), amount);
};
