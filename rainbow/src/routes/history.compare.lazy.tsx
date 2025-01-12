import { HistoryChart } from "@/charts/history/chart";
import { ALL_GAMEMODE_KEYS, ALL_STAT_KEYS } from "@/charts/history/types";
import { getHistoryQueryOptions } from "@/queries/history";
import { useQueries } from "@tanstack/react-query";
import { createLazyFileRoute, getRouteApi } from "@tanstack/react-router";
import React, { useMemo } from "react";

export const Route = createLazyFileRoute("/history/compare")({
    component: Index,
});

const route = getRouteApi("/history/compare");

interface KeySelectorProps<T extends string> {
    keys: readonly T[];
    selectedKeys: T[];
    defaultKey: T;
    onChange: (keys: T[]) => void;
}

function KeySelector<T extends string>({
    keys,
    selectedKeys,
    defaultKey,
    onChange,
}: KeySelectorProps<T>) {
    return (
        <div>
            {keys.map((key) => (
                <label key={key}>
                    <input
                        type="checkbox"
                        checked={selectedKeys.includes(key)}
                        onClick={() => {
                            if (selectedKeys.includes(key)) {
                                const filtered = selectedKeys.filter(
                                    (k) => k !== key,
                                );
                                if (filtered.length === 0) {
                                    onChange([defaultKey]);
                                } else {
                                    onChange(filtered);
                                }
                            } else {
                                onChange([...selectedKeys, key]);
                            }
                        }}
                    />
                    {key}
                </label>
            ))}
        </div>
    );
}

const toDatetimeLocal = (date: Date) => {
    // FIXME: Hacky, and probably not entirely correct
    const newDate = new Date(
        date.getTime() - date.getTimezoneOffset() * 60 * 1000,
    );
    return newDate.toISOString().slice(0, 16);
};

function Index() {
    const { uuids, stats, gamemodes, variant, start, end, limit } =
        route.useSearch();
    const navigate = route.useNavigate();

    const historyQueries = useQueries({
        queries: uuids.map((uuid) =>
            getHistoryQueryOptions({ uuid, start, end, limit }),
        ),
    });

    /*
    const { data, status, error } = useQueries({
    if (status === "pending") {
        return <div>Loading...</div>;
    }

    if (status === "error") {
        return <div>Error: {error.message}</div>;
    }
    */

    const finishedHistories = useMemo(() => {
        return historyQueries
            .filter((query) => query.status === "success")
            .map((query) => query.data);
    }, [historyQueries]);

    return (
        <div>
            <h3>Welcome Home!</h3>
            <KeySelector
                keys={ALL_STAT_KEYS}
                selectedKeys={stats}
                defaultKey="fkdr"
                onChange={(keys) => {
                    navigate({
                        search: (oldSearch) => ({
                            ...oldSearch,
                            stats: keys,
                        }),
                    }).catch((error: unknown) => {
                        // TODO: Handle error
                        console.error(
                            "Failed to update search params: stats",
                            error,
                        );
                    });
                }}
            />
            <br />
            <KeySelector
                keys={ALL_GAMEMODE_KEYS}
                selectedKeys={gamemodes}
                defaultKey="overall"
                onChange={(keys) => {
                    navigate({
                        search: (oldSearch) => ({
                            ...oldSearch,
                            gamemodes: keys,
                        }),
                    }).catch((error: unknown) => {
                        // TODO: Handle error
                        console.error(
                            "Failed to update search params: gamemode",
                            error,
                        );
                    });
                }}
            />

            <br />

            <label>
                <input
                    type="checkbox"
                    checked={variant === "session"}
                    onClick={() => {
                        const newVariant =
                            variant === "session" ? "overall" : "session";
                        navigate({
                            search: (oldSearch) => ({
                                ...oldSearch,
                                variant: newVariant,
                            }),
                        }).catch((error: unknown) => {
                            // TODO: Handle error
                            console.error(
                                "Failed to update search params: variant",
                                error,
                            );
                        });
                    }}
                />
                Session?
            </label>
            <br />

            <br />
            <label>
                Start:{" "}
                <input
                    type="datetime-local"
                    value={toDatetimeLocal(start)}
                    onChange={(e) => {
                        const newDate = new Date(e.target.value);
                        navigate({
                            search: (oldSearch) => ({
                                ...oldSearch,
                                start: newDate,
                            }),
                        }).catch((error: unknown) => {
                            // TODO: Handle error
                            console.error(
                                "Failed to update search params: start",
                                error,
                            );
                        });
                    }}
                />
            </label>

            <br />
            <label>
                End:{" "}
                <input
                    type="datetime-local"
                    value={toDatetimeLocal(end)}
                    onChange={(e) => {
                        const newDate = new Date(e.target.value);
                        navigate({
                            search: (oldSearch) => ({
                                ...oldSearch,
                                end: newDate,
                            }),
                        }).catch((error: unknown) => {
                            // TODO: Handle error
                            console.error(
                                "Failed to update search params: end",
                                error,
                            );
                        });
                    }}
                />
            </label>

            <HistoryChart
                histories={finishedHistories}
                gamemodes={gamemodes}
                stats={stats}
                variant={variant}
            />
        </div>
    );
}
