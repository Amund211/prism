import { ChartData } from "#charts/history/data.ts";
import { DataKey } from "#charts/history/dataKeys.ts";
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
    const [lastDataMax, setLastDataMax] = React.useState<number | undefined>();

    if (!synchronized) {
        return { synchronized: false };
    }

    const dataMax = chartData.reduce((max, data) => {
        return Math.max(max, data[dataKey] ?? 0);
    }, 0);
    if (lastDataMax !== dataMax) {
        setLastDataMax(dataMax);
        onYMaxChange(dataMax);
    }

    return { synchronized: true, yMax };
};
