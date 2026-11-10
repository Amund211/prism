import React from "react";

export interface KnownAliasesContextValue {
    readonly knownAliases: Readonly<Record<string, readonly string[] | undefined>>;
    readonly addKnownAlias: (alias: {
        readonly uuid: string;
        readonly username: string;
    }) => void;
}

export const KnownAliasesContext = React.createContext<KnownAliasesContextValue | null>(
    null,
);
