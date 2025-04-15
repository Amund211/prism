import React from "react";

export interface PlayerVisitsContextValue {
    favoriteUUIDs: string[];
    orderUUIDsByScore: (uuids: string[], currentUser?: string) => string[];
    visitPlayer: (uuid: string) => void;
    removePlayerVisits: (uuid: string) => void;
}

export const PlayerVisitsContext =
    React.createContext<PlayerVisitsContextValue | null>(null);
