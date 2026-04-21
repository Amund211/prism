import React from "react";

import { isNormalizedUUID } from "#helpers/uuid.ts";
import { useLocalStorage } from "#hooks/useLocalStorage.ts";

import { CurrentUserContext } from "./context.ts";
import { parseStoredUUID, localStorageKey } from "./helpers.ts";

export const CurrentUserProvider: React.FC<{
    children: React.ReactNode;
}> = ({ children }) => {
    const [storedCurrentUser, setStoredCurrentUser] = useLocalStorage(localStorageKey);
    const currentUser = parseStoredUUID(storedCurrentUser);

    const setCurrentUser = React.useCallback(
        (newUUID: string | null) => {
            if (newUUID !== null && !isNormalizedUUID(newUUID)) {
                throw new Error(`UUID not normalized: ${newUUID}`);
            }

            setStoredCurrentUser(newUUID);
        },
        [setStoredCurrentUser],
    );

    const value = React.useMemo(
        () => ({ currentUser, setCurrentUser }),
        [currentUser, setCurrentUser],
    );

    return (
        <CurrentUserContext.Provider value={value}>
            {children}
        </CurrentUserContext.Provider>
    );
};
