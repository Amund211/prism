import { queryOptions } from "@tanstack/react-query";

import { flashlightFetch } from "#helpers/flashlight/fetch.ts";
import { FlashlightResponseError } from "#helpers/flashlight/request.ts";

export interface APICredential {
    readonly clientType: string;
    // RFC 3339, UTC.
    readonly createdAt: string;
    readonly lastUsedAt: string;
}

interface APICredentialsResponse {
    readonly credentials: readonly APICredential[];
}

export const credentialsQueryKey = ["credentials"] as const;

/**
 * The signed-in identity's active sign-ins, newest first. Never persisted to
 * IndexedDB.
 *
 * Throws a FlashlightResponseError with status 403 when the session is not
 * microsoft.
 */
export const getCredentialsQueryOptions = (uuid: string | undefined) =>
    queryOptions({
        // The uuid keeps one account's list from showing for another.
        queryKey: [...credentialsQueryKey, uuid ?? null],
        queryFn: async (): Promise<readonly APICredential[]> => {
            const data = await flashlightFetch<APICredentialsResponse>(
                "/v1/auth/credentials",
                {
                    errorContext: "Failed to list sign-ins",
                    extra: {},
                    expectedStatuses: [403],
                },
            );
            return data.credentials;
        },
        meta: { persist: false },
        // A 403 means the session is not microsoft: retrying cannot help.
        retry: (failureCount, error) =>
            !(error instanceof FlashlightResponseError && error.status === 403) &&
            failureCount < 3,
    });
