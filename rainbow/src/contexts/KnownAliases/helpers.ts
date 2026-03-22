import { isNormalizedUUID } from "#helpers/uuid.ts";
import { makeLocalStorageWrite } from "#hooks/useLocalStorage.ts";

export const localStorageKey = "knownAliases";

const loadedAt = new Date();

interface AliasInfo {
    username: string;
    lastResolved: Date;
}

export type KnownAliases = Record<string, AliasInfo[] | undefined>;

export const stringifyKnownAliases = (aliases: KnownAliases): string => {
    const toStore: Record<string, { username: string; lastResolved: string }[]> = {};

    for (const [uuid, aliasInfos] of Object.entries(aliases)) {
        if (aliasInfos === undefined) {
            continue;
        }
        toStore[uuid] = aliasInfos.map((info) => ({
            username: info.username,
            lastResolved: info.lastResolved.toISOString(),
        }));
    }

    return JSON.stringify(toStore);
};

export const parseStoredAliases = (stored: string | null): KnownAliases => {
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

    const storedAliases: KnownAliases = {};
    for (const uuid in rawParsed) {
        if (!isNormalizedUUID(uuid)) {
            continue;
        }

        const value = (rawParsed as Record<string, unknown>)[uuid];
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

        storedAliases[uuid] = validAliases;
    }

    return storedAliases;
};

export const addKnownAlias = (
    aliases: KnownAliases,
    alias: { uuid: string; username: string },
) => {
    if (!isNormalizedUUID(alias.uuid)) {
        throw new Error(`UUID not normalized: ${alias.uuid}`);
    }

    const oldPlayerAliases = aliases[alias.uuid] ?? [];
    return {
        ...aliases,
        [alias.uuid]: [
            ...oldPlayerAliases.filter(
                (info) => info.username.toLowerCase() !== alias.username.toLowerCase(),
            ),
            {
                username: alias.username,
                lastResolved: new Date(),
            },
        ],
    };
};

const writeToLocalStorage = makeLocalStorageWrite(localStorageKey);
export const addKnownAliasAndPersist = (alias: {
    uuid: string;
    username: string;
}): void => {
    const aliases = parseStoredAliases(localStorage.getItem(localStorageKey));
    const newAliases = addKnownAlias(aliases, alias);
    const stringified = stringifyKnownAliases(newAliases);
    writeToLocalStorage(stringified);
};

// Convert known aliases to a map uuid -> username[] while filtering out old aliases
export const presentRecentKnownAliases = (
    aliases: KnownAliases,
): Record<string, string[] | undefined> => {
    return Object.fromEntries(
        Object.entries(aliases).map(([uuid, aliases]) => [
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
