import React from "react";
import { ChartSynchronizerContext } from "./context";

export const ChartSynchronizerProvider: React.FC<{
    children: React.ReactNode;
    queryKey: string;
}> = ({ children, queryKey }) => {
    const [yMax, setYMax] = React.useState<number | undefined>(undefined);

    const onYMaxChange = React.useCallback((yMax: number) => {
        setYMax((oldYMax) => Math.max(oldYMax ?? 0, yMax));
    }, []);

    const [previousQueryKey, setPreviousQueryKey] = React.useState<string>();
    if (previousQueryKey !== queryKey) {
        setYMax(undefined);
        setPreviousQueryKey(queryKey);
    }

    // The chart looks a bit silly if the domain is [0, 0], so we set the max to 1 so it displays at the bottom
    const yMaxWithShiftedZero = yMax === 0 ? 1 : yMax;

    return (
        <ChartSynchronizerContext.Provider
            value={{
                yMax: yMaxWithShiftedZero,
                onYMaxChange,
                synchronized: true,
            }}
        >
            {children}
        </ChartSynchronizerContext.Provider>
    );
};
