import React from "react";
import { KnownAliasesContext } from "./context.ts";
import {
    addKnownAlias,
    persistKnownAliases,
    presentRecentKnownAliases,
    usePersistedKnownAliases,
} from "./helpers.ts";

export const KnownAliasesProvider: React.FC<{
    children: React.ReactNode;
}> = ({ children }) => {
    const persistedKnownAliases = usePersistedKnownAliases();
    const [knownAliases, setKnownAliases] = React.useState(
        persistedKnownAliases,
    );

    // Update the state on this page when the persisted value has changed in another tab
    React.useEffect(() => {
        setKnownAliases(persistedKnownAliases);
    }, [persistedKnownAliases]);

    const addKnownAliasAndPersist = (alias: {
        uuid: string;
        username: string;
    }) => {
        const newAliases = addKnownAlias(knownAliases, alias);
        setKnownAliases(newAliases);
        persistKnownAliases(newAliases);
    };

    return (
        <KnownAliasesContext.Provider
            value={{
                knownAliases: presentRecentKnownAliases(knownAliases),
                addKnownAlias: addKnownAliasAndPersist,
            }}
        >
            {children}
        </KnownAliasesContext.Provider>
    );
};
