import {
    localStorageKey as currentUserKey,
    parseStoredUUID,
} from "#contexts/CurrentUser/helpers.ts";
import {
    localStorageKey as playerVisitsKey,
    orderPlayers,
    parseStoredPlayerVisits,
} from "#contexts/PlayerVisits/helpers.ts";

const MAX_FAVORITES = 5;

/**
 * The favorites shown on the landing page: the current user first, then the
 * most-visited players.
 */
export const selectFavoriteUUIDs = (
    favoriteUUIDs: readonly string[],
    currentUser: string | null,
): string[] =>
    (currentUser === null
        ? favoriteUUIDs
        : [currentUser, ...favoriteUUIDs.filter((uuid) => uuid !== currentUser)]
    ).slice(0, MAX_FAVORITES);

/**
 * The same favorites, read straight from local storage so a route loader can
 * prefetch their usernames before the providers have mounted.
 */
export const favoriteUUIDsFromStorage = (): string[] =>
    selectFavoriteUUIDs(
        orderPlayers(parseStoredPlayerVisits(localStorage.getItem(playerVisitsKey))),
        parseStoredUUID(localStorage.getItem(currentUserKey)),
    );
