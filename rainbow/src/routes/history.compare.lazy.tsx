import { HistoryChart } from "@/charts/history/chart";
import { ALL_GAMEMODE_KEYS, ALL_STAT_KEYS } from "@/charts/history/types";
import { createLazyFileRoute, getRouteApi } from "@tanstack/react-router";

export const Route = createLazyFileRoute("/history/compare")({
    component: Index,
});

const route = getRouteApi("/history/compare");

interface KeySelectorProps<T extends string> {
    keys: readonly T[];
    selectedKeys: T[];
    onChange: (keys: T[]) => void;
}

function KeySelector<T extends string>({
    keys,
    selectedKeys,
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
                                onChange(filtered);
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

    /*
    const { data, status, error } = useQueries({
    if (status === "pending") {
        return <div>Loading...</div>;
    }

    if (status === "error") {
        return <div>Error: {error.message}</div>;
    }
    */

    return (
        <div>
            <h3>Welcome Home!</h3>
            <KeySelector
                keys={[
                    "a937646b-f115-44c3-8dbf-9ae4a65669a0", // Skydeath
                    "ac04f297-f74c-44de-a24e-0083936ac59a", // USBB
                    "062c373b-28de-4ec0-ab2c-0114e59e36ce", // Skydeaf
                    "3d58a2de-3831-4a17-a305-67258295f81e", // iCiara
                    "6bc1dd0f-f351-4c3d-b6cc-262e55b6e7aa", // HardcoreLizard
                ]}
                selectedKeys={uuids}
                onChange={(keys) => {
                    navigate({
                        search: (oldSearch) => ({
                            ...oldSearch,
                            uuids: keys,
                        }),
                    }).catch((error: unknown) => {
                        // TODO: Handle error
                        console.error(
                            "Failed to update search params: uuids",
                            error,
                        );
                    });
                }}
            />
            <br />
            <KeySelector
                keys={ALL_STAT_KEYS}
                selectedKeys={stats}
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
                start={start}
                end={end}
                uuids={uuids}
                gamemodes={gamemodes}
                stats={stats}
                variant={variant}
                limit={limit}
            />
        </div>
    );
}
