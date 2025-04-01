import { type ChartData } from "#charts/history/data.ts";
import { type DataKey } from "#charts/history/dataKeys.ts";
import React from "react";
import { ChartSynchronizerContext } from "./context.ts";

export const useSynchronizeCharts = (
    chartData: ChartData,
    dataKey: DataKey,
):
    | { yMax: number | undefined; synchronized: true }
    | { yMax?: undefined; synchronized: false } => {
    const { synchronized, yMax, onYMaxChange } = React.use(
        ChartSynchronizerContext,
    );
    const dataMax = chartData.reduce((max, data) => {
        return Math.max(max, data[dataKey] ?? 0);
    }, 0);

    React.useEffect(() => {
        // Make sure to call this in an effect so we don't get set the state of a parent during render
        onYMaxChange?.(dataMax);
    }, [dataMax, onYMaxChange]);

    if (!synchronized) {
        return { synchronized: false };
    }

    return { synchronized: true, yMax };
};
