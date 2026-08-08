import { captureMessage } from "@sentry/react";
import { queryOptions, useQueries } from "@tanstack/react-query";

import { addKnownAliasAndPersist } from "#contexts/KnownAliases/helpers.ts";
import { flashlightFetch } from "#helpers/flashlight/fetch.ts";
import { isNormalizedUUID } from "#helpers/uuid.ts";
import { MS_PER_HOUR } from "#time.ts";

// Response of the flashlight `/v1/account/uuid/:uuid` endpoint.
export type APIUsernameResponse =
    | { readonly success: true; readonly username: string; readonly uuid: string }
    | { readonly success: false; readonly uuid: string; readonly cause: string };

export const getUsernameQueryOptions = (uuid: string) =>
    queryOptions({
        staleTime: MS_PER_HOUR,
        queryKey: ["username", uuid],
        queryFn: async (): Promise<{ uuid: string; username: string }> => {
            if (!isNormalizedUUID(uuid)) {
                captureMessage("Failed to get username: uuid is not normalized", {
                    level: "error",
                    extra: {
                        uuid,
                    },
                });
                throw new Error(`UUID not normalized: ${uuid}`);
            }

            const data = await flashlightFetch<unknown>(`/v1/account/uuid/${uuid}`, {
                errorContext: "Failed to get username",
                extra: { uuid },
            });
            if (typeof data !== "object" || data === null) {
                captureMessage("Failed to get username: invalid response", {
                    level: "error",
                    extra: {
                        uuid,
                        data,
                    },
                });
                throw new Error("Invalid response from flashlight api");
            }
            if (!("username" in data)) {
                captureMessage("Failed to get username: no username in response", {
                    level: "error",
                    extra: {
                        uuid,
                        data,
                    },
                });
                throw new Error("No username in response from flashlight api");
            }
            if (typeof data.username !== "string") {
                captureMessage("Failed to get username: username is not a string", {
                    level: "error",
                    extra: {
                        uuid,
                        data,
                    },
                });
                throw new Error("Invalid username in response from flashlight api");
            }

            addKnownAliasAndPersist({
                uuid,
                username: data.username,
            });

            return { uuid, username: data.username };
        },
    });

export const useUUIDToUsername = (uuids: readonly string[]) => {
    const usernameQueries = useQueries({
        queries: uuids.map((uuid) => getUsernameQueryOptions(uuid)),
    });

    const result: Record<string, string | undefined> = {};
    for (const query of usernameQueries) {
        if (query.status === "success") {
            result[query.data.uuid] = query.data.username;
        }
    }
    return result;
};
