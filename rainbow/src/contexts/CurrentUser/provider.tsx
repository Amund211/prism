import React from "react";
import { CurrentUserContext } from "./context.ts";
import {
    clearPersistedCurrentUser,
    getPersistedCurrentUser,
    setPersistedCurrentUser,
} from "./helpers.ts";

export const CurrentUserProvider: React.FC<{
    children: React.ReactNode;
}> = ({ children }) => {
    const [currentUser, setCurrentUser] = React.useState(() => {
        return getPersistedCurrentUser();
    });

    const setCurrentUserAndPersist = (newUser: string | null) => {
        if (newUser === null) {
            clearPersistedCurrentUser();
        } else {
            setPersistedCurrentUser(newUser);
        }
        setCurrentUser(newUser);
    };

    return (
        <CurrentUserContext.Provider
            value={{
                currentUser,
                setCurrentUser: setCurrentUserAndPersist,
            }}
        >
            {children}
        </CurrentUserContext.Provider>
    );
};
