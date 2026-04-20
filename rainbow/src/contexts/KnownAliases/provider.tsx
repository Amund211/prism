import React from "react";
import { KnownAliasesContext } from "./context.ts";
import {
    addKnownAlias,
    parseStoredAliases,
    presentRecentKnownAliases,
    localStorageKey,
    stringifyKnownAliases,
} from "./helpers.ts";
import { isNormalizedUUID } from "#helpers/uuid.ts";
import { useLocalStorage } from "#hooks/useLocalStorage.ts";

export const KnownAliasesProvider: React.FC<{
    children: React.ReactNode;
}> = ({ children }) => {
    const [storedKnownAliases, setStoredKnownAliases] =
        useLocalStorage(localStorageKey);
    const knownAliases = parseStoredAliases(storedKnownAliases);

    const addKnownAliasAndPersist = React.useCallback(
        (alias: { readonly uuid: string; readonly username: string }) => {
            if (!isNormalizedUUID(alias.uuid)) {
                throw new Error(`UUID not normalized: ${alias.uuid}`);
            }

            const newAliases = addKnownAlias(knownAliases, alias);
            setStoredKnownAliases(stringifyKnownAliases(newAliases));
        },
        [knownAliases, setStoredKnownAliases],
    );

    const value = React.useMemo(
        () => ({
            knownAliases: presentRecentKnownAliases(knownAliases),
            addKnownAlias: addKnownAliasAndPersist,
        }),
        [knownAliases, addKnownAliasAndPersist],
    );

    return (
        <KnownAliasesContext.Provider value={value}>
            {children}
        </KnownAliasesContext.Provider>
    );
};
