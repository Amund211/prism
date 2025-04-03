import React from "react";

export interface KnownAliasesContextValue {
    knownAliases: Record<string, string[] | undefined>;
    addKnownAlias: (alias: { uuid: string; username: string }) => void;
}

export const KnownAliasesContext =
    React.createContext<KnownAliasesContextValue | null>(null);
