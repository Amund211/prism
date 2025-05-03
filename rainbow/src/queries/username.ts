import { queryOptions, useQueries } from "@tanstack/react-query";
import { env } from "#env.ts";
import { addKnownAliasWithoutRerendering } from "#contexts/KnownAliases/helpers.ts";
import { useKnownAliases } from "#contexts/KnownAliases/hooks.ts";
import { isNormalizedUUID } from "#helpers/uuid.ts";

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
                throw new Error(`UUID not normalized: ${uuid}`);
            }

            const response = await fetch(
                // TODO: Attribution
                `${env.VITE_MINETOOLS_API_URL}/uuid/${uuid}`,
            );
            if (!response.ok) {
                throw new Error(
                    `Failed to fetch username for uuid. ${response.status.toString()} - ${response.statusText}: ${await response.text()}`,
                );
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
