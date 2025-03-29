const localStorageKey = "knownAliases";

const loadedAt = new Date();

interface AliasInfo {
    username: string;
    lastResolved: Date;
}

const parseStoredAliases = (
    stored: string | null,
): Record<string, AliasInfo[] | undefined> => {
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

    const storedAliases: Record<string, AliasInfo[] | undefined> = {};
    for (const key in rawParsed) {
        const value = (rawParsed as Record<string, unknown>)[key];
        if (typeof value !== "object" || value === null) {
            continue;
        }

        if (!Array.isArray(value)) {
            continue;
        }

        const validAliases = value
            .map((rawAlias: unknown) => {
                if (typeof rawAlias !== "object" || rawAlias === null) {
                    return null;
                }

                if (
                    !("lastResolved" in rawAlias) ||
                    typeof rawAlias.lastResolved !== "string"
                ) {
                    return null;
                }
                const lastResolved = new Date(rawAlias.lastResolved);
                if (isNaN(lastResolved.getTime())) {
                    return null;
                }

                if (
                    !("username" in rawAlias) ||
                    typeof rawAlias.username !== "string" ||
                    rawAlias.username.length === 0
                ) {
                    return null;
                }

                return { lastResolved, username: rawAlias.username };
            })
            .filter((v) => v !== null);

        storedAliases[key] = validAliases;
    }

    return storedAliases;
};

export const addKnownAlias = (alias: { uuid: string; username: string }) => {
    const stored = localStorage.getItem(localStorageKey);
    const parsed = parseStoredAliases(stored);
    const oldAliases = parsed[alias.uuid] ?? [];
    parsed[alias.uuid] = [
        ...oldAliases.filter(
            (info) =>
                info.username.toLowerCase() !== alias.username.toLowerCase(),
        ),
        {
            username: alias.username,
            lastResolved: new Date(),
        },
    ];
    localStorage.setItem(localStorageKey, JSON.stringify(parsed));
};

export const getKnownAliases = (): Record<string, string[] | undefined> => {
    const stored = localStorage.getItem(localStorageKey);
    const parsed = parseStoredAliases(stored);
    return Object.fromEntries(
        Object.entries(parsed).map(([uuid, aliases]) => [
            uuid,
            aliases
                ?.filter(
                    (info) =>
                        // Only allow aliases that have been resolved in the last year
                        info.lastResolved.getTime() >
                        loadedAt.getTime() - 1000 * 60 * 60 * 24 * 30 * 12,
                )
                .map((info) => info.username) ?? [],
        ]),
    );
};
