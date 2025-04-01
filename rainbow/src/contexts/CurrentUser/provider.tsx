import React from "react";
import { CurrentUserContext } from "./context.ts";
import { persistCurrentUser, usePersistedCurrentUser } from "./helpers.ts";

export const CurrentUserProvider: React.FC<{
    children: React.ReactNode;
}> = ({ children }) => {
    const persistedCurrentUser = usePersistedCurrentUser();
    const [currentUser, setCurrentUser] = React.useState(persistedCurrentUser);

    // Update the state on this page when the persisted value has changed in another tab
    React.useEffect(() => {
        setCurrentUser(persistedCurrentUser);
    }, [persistedCurrentUser]);

    const setCurrentUserAndPersist = (newUser: string | null) => {
        persistCurrentUser(newUser);
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
