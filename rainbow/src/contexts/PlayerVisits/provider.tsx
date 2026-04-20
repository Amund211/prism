import React from "react";
import { PlayerVisitsContext } from "./context.ts";
import {
    orderPlayers,
    parseStoredPlayerVisits,
    removePlayerVisits,
    visitPlayer,
    localStorageKey,
    stringifyPlayerVisits,
} from "./helpers.ts";
import { isNormalizedUUID } from "#helpers/uuid.ts";
import { useLocalStorage } from "#hooks/useLocalStorage.ts";

export const PlayerVisitsProvider: React.FC<{
    children: React.ReactNode;
}> = ({ children }) => {
    const [storedPlayerVisits, setStoredPlayerVisits] =
        useLocalStorage(localStorageKey);
    const playerVisits = parseStoredPlayerVisits(storedPlayerVisits);

    const visitPlayerAndPersist = React.useCallback(
        (uuid: string) => {
            if (!isNormalizedUUID(uuid)) {
                throw new Error(`UUID not normalized: ${uuid}`);
            }

            const newVisits = visitPlayer(playerVisits, uuid);
            setStoredPlayerVisits(stringifyPlayerVisits(newVisits));
        },
        [playerVisits, setStoredPlayerVisits],
    );

    const removePlayerVisitsAndPersist = React.useCallback(
        (uuid: string) => {
            if (!isNormalizedUUID(uuid)) {
                throw new Error(`UUID not normalized: ${uuid}`);
            }

            const newVisits = removePlayerVisits(playerVisits, uuid);
            setStoredPlayerVisits(stringifyPlayerVisits(newVisits));
        },
        [playerVisits, setStoredPlayerVisits],
    );

    const favoriteUUIDs = orderPlayers(playerVisits);

    const orderUUIDsByScore = React.useCallback(
        (uuids: string[], currentUser?: string): string[] => {
            if (uuids.some((uuid) => !isNormalizedUUID(uuid))) {
                throw new Error(`Some UUIDs are not normalized: ${uuids.join(", ")}`);
            }

            return [...uuids].toSorted((a, b) => {
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
        },
        [favoriteUUIDs],
    );

    const value = React.useMemo(
        () => ({
            favoriteUUIDs,
            orderUUIDsByScore,
            visitPlayer: visitPlayerAndPersist,
            removePlayerVisits: removePlayerVisitsAndPersist,
        }),
        [
            favoriteUUIDs,
            orderUUIDsByScore,
            visitPlayerAndPersist,
            removePlayerVisitsAndPersist,
        ],
    );

    return (
        <PlayerVisitsContext.Provider value={value}>
            {children}
        </PlayerVisitsContext.Provider>
    );
};
