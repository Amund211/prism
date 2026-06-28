import { captureException, captureMessage } from "@sentry/react";
import { queryOptions } from "@tanstack/react-query";

import { env } from "#env.ts";
import { getOrSetUserId } from "#helpers/userId.ts";
import { isNormalizedUUID } from "#helpers/uuid.ts";
import { ALL_GAMEMODE_KEYS } from "#stats/keys.ts";
import type { GamemodeKey } from "#stats/keys.ts";
import { MS_PER_MINUTE } from "#time.ts";

import { apiToPlayerDataPIT } from "./playerdata.ts";
import type { APIPlayerDataPIT, PlayerDataPIT } from "./playerdata.ts";
import type { APISession, Session } from "./sessions.ts";
import { apiToSession } from "./sessions.ts";

// The real gamemodes — every GamemodeKey except the "overall" aggregate.
export type Gamemode = Exclude<GamemodeKey, "overall">;

const isGamemode = (value: unknown): value is Gamemode =>
    typeof value === "string" &&
    value !== "overall" &&
    (ALL_GAMEMODE_KEYS as readonly string[]).includes(value);

// How a single game ended. Draws are rare in Bedwars but do happen, so this is
// a three-state enum rather than a won/lost boolean. Mirrors the flashlight
// `session-at` wire contract (`"outcome": "win" | "loss" | "draw"`).
export const GAME_OUTCOMES = ["win", "loss", "draw"] as const;
export type GameOutcome = (typeof GAME_OUTCOMES)[number];

const isGameOutcome = (value: unknown): value is GameOutcome =>
    typeof value === "string" && (GAME_OUTCOMES as readonly string[]).includes(value);

interface APIGameResult {
    readonly gamemode: string;
    readonly outcome: string;
    readonly finalKills: number;
    readonly finalDeath: boolean;
    readonly bedsBroken: number;
    readonly bedLost: boolean;
    readonly kills: number;
    readonly deaths: number;
    readonly experience: number;
}

interface APIGameSegment {
    readonly start: APIPlayerDataPIT;
    readonly end: APIPlayerDataPIT;
    readonly game: APIGameResult | null;
}

export interface APISessionAtResponse {
    readonly session: APISession | null;
    readonly games: readonly APIGameSegment[];
}

export interface GameResult {
    readonly gamemode: Gamemode;
    readonly outcome: GameOutcome;
    readonly finalKills: number;
    // Booleans: at most one final death and one bed lost happen per game.
    readonly finalDeath: boolean;
    readonly bedsBroken: number;
    readonly bedLost: boolean;
    readonly kills: number;
    readonly deaths: number;
    readonly experience: number;
}

export interface GameSegment {
    readonly start: PlayerDataPIT;
    readonly end: PlayerDataPIT;
    // null when the snapshot pair represents zero games (no game played) or
    // more than one game (gamesPlayed jumped by 2+, or multiple modes
    // advanced). Callers should render these specially — e.g. "(no games)"
    // for no-game windows or "(N games played)" for ambiguous stretches.
    readonly game: GameResult | null;
}

export interface SessionAt {
    readonly session: Session | null;
    readonly games: readonly GameSegment[];
}

const apiToGameResult = (api: APIGameResult): GameResult | null => {
    if (!isGamemode(api.gamemode)) {
        captureMessage("Unknown gamemode in session-at response", {
            level: "error",
            extra: { gamemode: api.gamemode },
        });
        return null;
    }
    if (!isGameOutcome(api.outcome)) {
        captureMessage("Unknown outcome in session-at response", {
            level: "error",
            extra: { outcome: api.outcome },
        });
        return null;
    }
    return {
        gamemode: api.gamemode,
        outcome: api.outcome,
        finalKills: api.finalKills,
        finalDeath: api.finalDeath,
        bedsBroken: api.bedsBroken,
        bedLost: api.bedLost,
        kills: api.kills,
        deaths: api.deaths,
        experience: api.experience,
    };
};

interface SessionAtQueryOptions {
    readonly uuid: string;
    readonly time: Date;
}

// How often to refetch while a session is still ongoing. Games last a few
// minutes, so a minute keeps the LIVE badge honest without hammering the API.
const ONGOING_REFETCH_MS = MS_PER_MINUTE;

export const getSessionAtQueryOptions = ({ uuid, time }: SessionAtQueryOptions) => {
    const timeISOString = time.toISOString();

    return queryOptions({
        // An ended session is immutable, so cache it forever. An ongoing one
        // keeps changing behind the LIVE badge, so let it go stale and refetch
        // on an interval — otherwise the "live" numbers freeze at first load.
        staleTime: (query) =>
            query.state.data?.session?.ongoing === true ? ONGOING_REFETCH_MS : Infinity,
        refetchInterval: (query) =>
            query.state.data?.session?.ongoing === true ? ONGOING_REFETCH_MS : false,
        queryKey: ["sessionAt", uuid, timeISOString],
        queryFn: async (): Promise<SessionAt> => {
            if (!isNormalizedUUID(uuid)) {
                captureMessage("Failed to get session-at: uuid is not normalized", {
                    level: "error",
                    extra: { uuid, time: timeISOString },
                });
                throw new Error(`UUID not normalized: ${uuid}`);
            }

            const response = await fetch(
                // NOTE: The flashlight API does **not** allow third-party access.
                //       Do not send any requests to any endpoints without explicit permission.
                //       Reach out on Discord for more information. https://discord.gg/k4FGUnEHYg
                `${env.VITE_FLASHLIGHT_URL}/v1/session-at`,
                {
                    headers: {
                        "Content-Type": "application/json",
                        "X-User-Id": getOrSetUserId(),
                    },
                    method: "POST",
                    body: JSON.stringify({ uuid, time: timeISOString }),
                },
            ).catch((error: unknown) => {
                captureException(error, {
                    extra: {
                        uuid,
                        time: timeISOString,
                        message: "Failed to get session-at: failed to fetch",
                    },
                });
                throw error;
            });

            if (!response.ok) {
                const text = await response.text().catch(() => "");
                captureMessage("Failed to get session-at: response error", {
                    level: "error",
                    tags: {
                        status: response.status,
                        statusText: response.statusText,
                    },
                    extra: { uuid, time: timeISOString, text },
                });
                throw new Error(
                    `Failed to fetch session-at. ${response.status.toString()} - ${response.statusText}`,
                );
            }

            const data = (await response.json().catch((error: unknown) => {
                captureException(error, {
                    extra: {
                        uuid,
                        time: timeISOString,
                        message: "Failed to get session-at: failed to parse json",
                    },
                });
                throw error;
            })) as APISessionAtResponse;

            return {
                session:
                    data.session === null ? null : apiToSession(data.session, false),
                games: data.games.map(
                    (seg): GameSegment => ({
                        start: apiToPlayerDataPIT(seg.start),
                        end: apiToPlayerDataPIT(seg.end),
                        game: seg.game === null ? null : apiToGameResult(seg.game),
                    }),
                ),
            };
        },
    });
};
