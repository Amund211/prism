import { queryOptions, useQueries } from "@tanstack/react-query";
import { env } from "#env.ts";
import { addKnownAlias } from "#helpers/knownAliases.ts";

export const getUsernameQueryOptions = (uuid: string) =>
    queryOptions({
        staleTime: 1000 * 60 * 60,
        queryKey: ["username", uuid],
        queryFn: async (): Promise<{ uuid: string; username: string }> => {
            const response = await fetch(
                // TODO: Attribution
                `${env.VITE_MINETOOLS_API_URL}/uuid/${uuid}`,
            );
            if (!response.ok) {
                throw new Error(`Failed to fetch data: ${response.statusText}`);
            }

            const data: unknown = await response.json();
            if (typeof data !== "object" || data === null) {
                throw new Error("Invalid response from minetools");
            }
            if (!("name" in data)) {
                throw new Error("No name in response from minetools");
            }
            if (typeof data.name !== "string") {
                throw new Error("Invalid name in response from minetools");
            }

            addKnownAlias({ uuid, username: data.name });

            return { uuid, username: data.name };
        },
    });

export const useUUIDToUsername = (uuids: readonly string[]) => {
    const usernameQueries = useQueries({
        queries: uuids.map((uuid) => getUsernameQueryOptions(uuid)),
    });

    const result: Record<string, string | undefined> = {};
    usernameQueries.forEach((query) => {
        if (query.status === "success") {
            result[query.data.uuid] = query.data.username;
        }
    });
    return result;
};
