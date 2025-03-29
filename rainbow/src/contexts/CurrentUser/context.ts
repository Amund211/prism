import React from "react";

export interface CurrentUserContextValue {
    currentUser: string | null;
    setCurrentUser: (u: string | null) => void;
}

export const CurrentUserContext =
    React.createContext<CurrentUserContextValue | null>(null);
