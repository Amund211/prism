import { queryOptions, useQueries } from "@tanstack/react-query";
import { env } from "#env.ts";
import { addKnownAliasWithoutRerendering } from "#contexts/KnownAliases/helpers.ts";
import { useKnownAliases } from "#contexts/KnownAliases/hooks.ts";
import { isNormalizedUUID } from "#helpers/uuid.ts";
import { captureException, captureMessage } from "@sentry/react";

export const getUsernameQueryOptions = (
    uuid: string,
    addKnownAlias?: (alias: { uuid: string; username: string }) => void,
) =>
    queryOptions({
        staleTime: 1000 * 60 * 60,
        // The query does not depend on our addKnownAlias side-effect
        // eslint-disable-next-line @tanstack/query/exhaustive-deps
        queryKey: ["username", uuid],
        queryFn: async (): Promise<{ uuid: string; username: string }> => {
            if (!isNormalizedUUID(uuid)) {
                captureMessage(
                    "Failed to get username: uuid is not normalized",
                    {
                        level: "error",
                        extra: {
                            uuid,
                        },
                    },
                );
                throw new Error(`UUID not normalized: ${uuid}`);
            }

            const response = await fetch(
                `${env.VITE_MINETOOLS_API_URL}/uuid/${uuid}`,
            ).catch((error: unknown) => {
                captureException(error, {
                    extra: {
                        uuid,
                        message: "Failed to get username: failed to fetch",
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
                                "Failed to get username: failed to read response text when handling response error",
                            uuid,
                        },
                    });
                    throw error;
                });
                captureMessage("Failed to get username: response error", {
                    level: "error",
                    tags: {
                        status: response.status,
                        statusText: response.statusText,
                    },
                    extra: {
                        text,
                    },
                });
                throw new Error(
                    `Failed to fetch username for uuid. ${response.status.toString()} - ${response.statusText}: ${await response.text()}`,
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
                                        "Failed to get username: failed to parse json",
                                    uuid,
                                    text,
                                },
                            });
                        })
                        .catch((textError: unknown) => {
                            captureException(textError, {
                                extra: {
                                    message:
                                        "Failed to get username: failed to read response text when handling response error",
                                    uuid,
                                    jsonParseError: error,
                                },
                            });
                        });
                });
            if (typeof data !== "object" || data === null) {
                captureMessage("Failed to get username: invalid response", {
                    level: "error",
                    extra: {
                        uuid,
                        data,
                    },
                });
                throw new Error("Invalid response from minetools");
            }
            if (!("name" in data)) {
                captureMessage("Failed to get username: no name in response", {
                    level: "error",
                    extra: {
                        uuid,
                        data,
                    },
                });
                throw new Error("No name in response from minetools");
            }
            if (typeof data.name !== "string") {
                captureMessage("Failed to get username: name is not a string", {
                    level: "error",
                    extra: {
                        uuid,
                        data,
                    },
                });
                throw new Error("Invalid name in response from minetools");
            }

            if (addKnownAlias) {
                addKnownAlias({ uuid, username: data.name });
            } else {
                addKnownAliasWithoutRerendering({ uuid, username: data.name });
            }

            return { uuid, username: data.name };
        },
    });

export const useUUIDToUsername = (uuids: readonly string[]) => {
    const { addKnownAlias } = useKnownAliases();
    const usernameQueries = useQueries({
        queries: uuids.map((uuid) =>
            getUsernameQueryOptions(uuid, addKnownAlias),
        ),
    });

    const result: Record<string, string | undefined> = {};
    usernameQueries.forEach((query) => {
        if (query.status === "success") {
            result[query.data.uuid] = query.data.username;
        }
    });
    return result;
};
