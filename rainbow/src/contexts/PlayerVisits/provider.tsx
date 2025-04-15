import React from "react";
import { PlayerVisitsContext } from "./context.ts";
import {
    orderPlayers,
    persistPlayerVisits,
    removePlayerVisits,
    usePersistedPlayerVisits,
    visitPlayer,
} from "./helpers.ts";

export const PlayerVisitsProvider: React.FC<{
    children: React.ReactNode;
}> = ({ children }) => {
    const persistedPlayerVisits = usePersistedPlayerVisits();
    const [playerVisits, setPlayerVisits] = React.useState(
        persistedPlayerVisits,
    );

    // Update the state on this page when the persisted value has changed in another tab
    React.useEffect(() => {
        setPlayerVisits(persistedPlayerVisits);
    }, [persistedPlayerVisits]);

    const visitPlayerAndPersist = (uuid: string) => {
        const newVisits = visitPlayer(playerVisits, uuid);
        setPlayerVisits(newVisits);
        persistPlayerVisits(newVisits);
    };

    const removePlayerVisitsAndPersist = (uuid: string) => {
        const newVisits = removePlayerVisits(playerVisits, uuid);
        setPlayerVisits(newVisits);
        persistPlayerVisits(newVisits);
    };

    const favoriteUUIDs = orderPlayers(playerVisits);

    const orderUUIDsByScore = (
        uuids: string[],
        currentUser?: string,
    ): string[] => {
        return [...uuids].sort((a, b) => {
            // If provided with a current user, sort them to the top
            if (currentUser !== undefined) {
                if (a === currentUser) return -1;
                if (b === currentUser) return 1;
            }

            const aIndex = favoriteUUIDs.indexOf(a);
            const bIndex = favoriteUUIDs.indexOf(b);
            if (aIndex === -1) return 1;
            if (bIndex === -1) return -1;
            return aIndex - bIndex;
        });
    };

    return (
        <PlayerVisitsContext.Provider
            value={{
                favoriteUUIDs,
                orderUUIDsByScore,
                visitPlayer: visitPlayerAndPersist,
                removePlayerVisits: removePlayerVisitsAndPersist,
            }}
        >
            {children}
        </PlayerVisitsContext.Provider>
    );
};
