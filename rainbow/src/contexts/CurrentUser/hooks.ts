import React from "react";
import { CurrentUserContext } from "./context.ts";
import type { CurrentUserContextValue } from "./context.ts";

export const useCurrentUser = (): CurrentUserContextValue => {
    const value = React.use(CurrentUserContext);
    if (value === null) {
        throw new Error("useCurrentUser must be used within a CurrentUserProvider");
    }
    return value;
};
