import type { QueryClient, QueryExecuteOptions, QueryKey } from "@tanstack/react-query";

/**
 * Warm the cache for a query, ignoring errors. Replaces the deprecated
 * `queryClient.prefetchQuery`.
 */
export const prefetchQuery = async <
    TQueryFnData,
    TError,
    TData,
    TQueryKey extends QueryKey,
>(
    queryClient: QueryClient,
    options: QueryExecuteOptions<TQueryFnData, TError, TData, TQueryFnData, TQueryKey>,
): Promise<void> => {
    try {
        await queryClient.query(options);
    } catch {
        // The useQuery that reads this key surfaces the error.
    }
};
