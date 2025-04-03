import { queryOptions } from "@tanstack/react-query";
import { env } from "#env.ts";
import { normalizeUUID } from "#helpers/uuid.ts";
import { addKnownAlias } from "#helpers/knownAliases.ts";

export const getUUIDQueryOptions = (username: string) =>
    queryOptions({
        staleTime: 1000 * 60 * 60 * 24 * 21,
        queryKey: ["uuid", username],
        queryFn: async (): Promise<{ uuid: string; username: string }> => {
            const response = await fetch(
                `${env.VITE_MINETOOLS_API_URL}/uuid/${username}`,
            );
            if (!response.ok) {
                throw new Error(
                    `Failed to fetch uuid for username. ${response.status.toString()} - ${response.statusText}: ${await response.text()}`,
                );
            }

            const data: unknown = await response.json();
            if (typeof data !== "object" || data === null) {
                throw new Error("Invalid response from minecraft services api");
            }
            if (!("id" in data)) {
                throw new Error(
                    "No uuid in response from minecraft services api",
                );
            }
            if (typeof data.id !== "string") {
                throw new Error(
                    "Invalid uuid in response from minecraft services api",
                );
            }

            const rawUUID = data.id;
            const uuid = normalizeUUID(rawUUID);

            addKnownAlias({ uuid, username });

            return { username, uuid };
        },
    });
