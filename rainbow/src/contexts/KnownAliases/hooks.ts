import React from "react";
import {
    KnownAliasesContext,
    type KnownAliasesContextValue,
} from "./context.ts";

export const useKnownAliases = (): KnownAliasesContextValue => {
    const value = React.use(KnownAliasesContext);
    if (value === null) {
        throw new Error(
            "useKnownAliases must be used within a KnownAliasesProvider",
        );
    }
    return value;
};
