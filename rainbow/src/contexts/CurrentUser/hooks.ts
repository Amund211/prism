import React from "react";
import { CurrentUserContext, CurrentUserContextValue } from "./context.ts";

export const useCurrentUser = (): CurrentUserContextValue => {
    const value = React.use(CurrentUserContext);
    if (value === null) {
        throw new Error(
            "useCurrentUser must be used within a CurrentUserProvider",
        );
    }
    return value;
};
