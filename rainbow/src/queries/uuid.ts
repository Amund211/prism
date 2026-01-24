import { queryOptions } from "@tanstack/react-query";
import { env } from "#env.ts";
import { normalizeUUID } from "#helpers/uuid.ts";
import { addKnownAliasWithoutRerendering } from "#contexts/KnownAliases/helpers.ts";
import { captureException, captureMessage } from "@sentry/react";
import { getOrSetUserId } from "#helpers/userId.ts";

export const getUUIDQueryOptions = (
    username: string,
    addKnownAlias?: (alias: { uuid: string; username: string }) => void,
) =>
    queryOptions({
        staleTime: 1000 * 60 * 60 * 24 * 21,
        // The query does not depend on our addKnownAlias side-effect
        // eslint-disable-next-line @tanstack/query/exhaustive-deps
        queryKey: ["uuid", username],
        queryFn: async (): Promise<{ uuid: string; username: string }> => {
            const response = await fetch(
                // NOTE: The flashlight API does **not** allow third-party access.
                //       Do not send any requests to any endpoints without explicit permission.
                //       Reach out on Discord for more information. https://discord.gg/k4FGUnEHYg
                `${env.VITE_FLASHLIGHT_URL}/v1/account/username/${username}`,
                {
                    headers: {
                        "X-User-Id": getOrSetUserId(),
                    },
                },
            ).catch((error: unknown) => {
                captureException(error, {
                    extra: {
                        username,
                        message: "Failed to get uuid: failed to fetch",
                    },
                });
                throw error;
            });

            if (!response.ok) {
                const text = await response.text().catch((error: unknown) => {
                    captureException(error, {
                        tags: {
                            status: response.status,
                            statusText: response.statusText,
                        },
                        extra: {
                            message:
                                "Failed to get uuid: failed to read response text when handling response error",
                            username,
                        },
                    });
                    throw error;
                });
                captureMessage("Failed to get uuid: response error", {
                    level: "error",
                    extra: {
                        status: response.status,
                        statusText: response.statusText,
                        text,
                    },
                });
                throw new Error(
                    `Failed to fetch uuid for username. ${response.status.toString()} - ${response.statusText}: ${text}`,
                );
            }

            const data: unknown = await response
                .json()
                .catch((error: unknown) => {
                    response
                        .text()
                        .then((text) => {
                            captureException(error, {
                                extra: {
                                    message:
                                        "Failed to get uuid: failed to parse json",
                                    username,
                                    text,
                                },
                            });
                        })
                        .catch((textError: unknown) => {
                            captureException(textError, {
                                tags: {
                                    status: response.status,
                                    statusText: response.statusText,
                                },
                                extra: {
                                    message:
                                        "Failed to get uuid: failed to read response text when handling json parse error",
                                    username,
                                    jsonParseError: error,
                                },
                            });
                            throw textError;
                        });
                    throw error;
                });

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
                throw new Error(
                    "No uuid in response from minecraft services api",
                );
            }
            if (typeof data.uuid !== "string") {
                captureMessage(
                    "Failed to get uuid: uuid is not a string in response",
                    {
                        level: "error",
                        extra: {
                            data,
                            username,
                        },
                    },
                );
                throw new Error(
                    "Invalid uuid in response from minecraft services api",
                );
            }

            const rawUUID = data.uuid;
            const uuid = normalizeUUID(rawUUID);
            if (!uuid) {
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

            if (addKnownAlias) {
                addKnownAlias({ uuid, username });
            } else {
                addKnownAliasWithoutRerendering({ uuid, username });
            }

            return { username, uuid };
        },
    });
