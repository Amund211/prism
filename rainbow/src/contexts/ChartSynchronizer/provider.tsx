import React from "react";

import { ChartSynchronizerContext } from "./context.ts";

export const ChartSynchronizerProvider: React.FC<{
    children: React.ReactNode;
    queryKey: string;
}> = ({ children, queryKey }) => {
    const [yMax, setYMax] = React.useState<number | undefined>(undefined);

    const onYMaxChange = React.useCallback((newYMax: number) => {
        setYMax((oldYMax) => Math.max(oldYMax ?? 0, newYMax));
    }, []);

    const [previousQueryKey, setPreviousQueryKey] = React.useState<string>();
    if (previousQueryKey !== queryKey) {
        setYMax(undefined);
        setPreviousQueryKey(queryKey);
    }

    // The chart looks a bit silly if the domain is [0, 0], so we set the max to 1 so it displays at the bottom
    const yMaxWithShiftedZero = yMax === 0 ? 1 : yMax;

    const value = React.useMemo(
        () =>
            ({
                yMax: yMaxWithShiftedZero,
                onYMaxChange,
                synchronized: true,
            }) as const,
        [yMaxWithShiftedZero, onYMaxChange],
    );

    return (
        <ChartSynchronizerContext.Provider value={value}>
            {children}
        </ChartSynchronizerContext.Provider>
    );
};
