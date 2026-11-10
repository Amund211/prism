import { captureMessage } from "@sentry/react";
import { queryOptions } from "@tanstack/react-query";

import { addKnownAliasAndPersist } from "#contexts/KnownAliases/helpers.ts";
import { flashlightFetch } from "#helpers/flashlight/fetch.ts";
import { normalizeUUID } from "#helpers/uuid.ts";
import { MS_PER_DAY } from "#time.ts";

// Response of the flashlight `/v1/account/username/:username` endpoint.
export type APIUUIDResponse =
    | { readonly success: true; readonly username: string; readonly uuid: string }
    | { readonly success: false; readonly username: string; readonly cause: string };

export const getUUIDQueryOptions = (username: string) =>
    queryOptions({
        staleTime: MS_PER_DAY * 21,
        queryKey: ["uuid", username],
        queryFn: async (): Promise<{ uuid: string; username: string }> => {
            const data = await flashlightFetch<unknown>(
                `/v1/account/username/${username}`,
                {
                    errorContext: "Failed to get uuid",
                    extra: { username },
                },
            );

            if (typeof data !== "object" || data === null) {
                captureMessage("Failed to get uuid: invalid response", {
                    level: "error",
                    extra: {
                        data,
                        username,
                    },
                });
                throw new Error("Invalid response from minecraft services api");
            }
            if (!("uuid" in data)) {
                captureMessage("Failed to get uuid: no uuid in response", {
                    level: "error",
                    extra: {
                        data,
                        username,
                    },
                });
                throw new Error("No uuid in response from minecraft services api");
            }
            if (typeof data.uuid !== "string") {
                captureMessage("Failed to get uuid: uuid is not a string in response", {
                    level: "error",
                    extra: {
                        data,
                        username,
                    },
                });
                throw new Error("Invalid uuid in response from minecraft services api");
            }

            const rawUUID = data.uuid;
            const uuid = normalizeUUID(rawUUID);
            if (uuid === null) {
                captureMessage("Failed to get uuid: failed to normalize uuid", {
                    level: "error",
                    extra: {
                        data,
                        rawUUID,
                        username,
                    },
                });
                throw new Error(
                    `Could not normalize uuid from minecraft services api: ${rawUUID}`,
                );
            }

            addKnownAliasAndPersist({ uuid, username });

            return { username, uuid };
        },
    });
