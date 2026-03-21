import React from "react";
import { CurrentUserContext } from "./context.ts";
import { parseStoredUUID, localStorageKey } from "./helpers.ts";
import { useLocalStorage } from "#hooks/useLocalStorage.ts";
import { isNormalizedUUID } from "#helpers/uuid.ts";

export const CurrentUserProvider: React.FC<{
    children: React.ReactNode;
}> = ({ children }) => {
    const [storedCurrentUser, setStoredCurrentUser] =
        useLocalStorage(localStorageKey);
    const currentUser = parseStoredUUID(storedCurrentUser);

    const setCurrentUser = (newUUID: string | null) => {
        if (newUUID !== null && !isNormalizedUUID(newUUID)) {
            throw new Error(`UUID not normalized: ${newUUID}`);
        }

        setStoredCurrentUser(newUUID);
    };

    return (
        <CurrentUserContext.Provider value={{ currentUser, setCurrentUser }}>
            {children}
        </CurrentUserContext.Provider>
    );
};
