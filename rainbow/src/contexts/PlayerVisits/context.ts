import React from "react";

export interface PlayerVisitsContextValue {
    readonly favoriteUUIDs: readonly string[];
    readonly orderUUIDsByScore: (
        uuids: readonly string[],
        currentUser?: string,
    ) => string[];
    readonly visitPlayer: (uuid: string) => void;
    readonly removePlayerVisits: (uuid: string) => void;
}

export const PlayerVisitsContext = React.createContext<PlayerVisitsContextValue | null>(
    null,
);
