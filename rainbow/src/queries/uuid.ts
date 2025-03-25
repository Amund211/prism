import { queryOptions } from "@tanstack/react-query";
import { env } from "#env.ts";

export const normalizeUUID = (uuid: string) => {
    const cleaned = uuid.replace(/[^\da-fA-F]/g, "").toLowerCase();

    if (cleaned.length !== 32) {
        throw new Error(`Invalid UUID: ${uuid}`);
    }

    return `${cleaned.slice(0, 8)}-${cleaned.slice(8, 12)}-${cleaned.slice(
        12,
        16,
    )}-${cleaned.slice(16, 20)}-${cleaned.slice(20)}`;
};

export const getUUIDQueryOptions = (username: string) =>
    queryOptions({
        staleTime: 1000 * 60 * 60,
        queryKey: ["uuid", username],
        queryFn: async (): Promise<{ uuid: string; username: string }> => {
            const response = await fetch(
                `${env.VITE_MINETOOLS_API_URL}/uuid/${username}`,
            );
            if (!response.ok) {
                throw new Error(`Failed to fetch data: ${response.statusText}`);
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

            return { username, uuid };
        },
    });
