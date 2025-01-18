import { type History } from "#queries/history.ts";
import {
    ALL_GAMEMODE_KEYS,
    ALL_STAT_KEYS,
    ALL_VARIANT_KEYS,
} from "#stats/keys.ts";
import { type DataKey, makeDataKey } from "./dataKeys.ts";
import { computeStat } from "#stats/index.ts";

type ChartDataEntry = Record<DataKey, number | undefined | null> & {
    queriedAt: number;
};

export type ChartData = ChartDataEntry[];

const generateChartDataFromSingleHistory = (history: History): ChartData => {
    const data: ChartData = [];
    for (const playerData of history) {
        const entry: ChartDataEntry = {
            queriedAt: playerData.queriedAt.getTime(),
        };
        for (const variant of ALL_VARIANT_KEYS) {
            for (const gamemode of ALL_GAMEMODE_KEYS) {
                for (const stat of ALL_STAT_KEYS) {
                    const key = makeDataKey({
                        uuid: playerData.uuid,
                        stat,
                        variant,
                        gamemode,
                    });

                    entry[key] = computeStat(
                        playerData,
                        gamemode,
                        stat,
                        variant,
                        history,
                    );
                }
            }
        }
        data.push(entry);
    }
    return data;
};

export const clusterChartData = (chartData: ChartData): ChartData => {
    if (chartData.length === 0) {
        return [];
    }

    const timeSpan =
        chartData[chartData.length - 1].queriedAt - chartData[0].queriedAt;
    // Cluster entries that are closer than 1% of the time span or 1 minute
    const threshold = Math.max(timeSpan / 100, 1000 * 60);

    const clusteredChartData: ChartData = [];
    for (let i = chartData.length - 1; i >= 0; i--) {
        const entry = chartData[i];
        let entriesToCluster = 1; // Number of entries to cluster, including this one
        while (
            i - entriesToCluster >= 0 &&
            entry.queriedAt - chartData[i - entriesToCluster].queriedAt <=
                threshold
        ) {
            entriesToCluster++;
        }
        for (let offset = 0; offset < entriesToCluster; offset++) {
            const newEntry = {
                ...chartData[i - offset],
                queriedAt: entry.queriedAt,
            };
            clusteredChartData.push(newEntry);
        }
        // Skip the entries that were clustered, the current entry is already skipped by the for loop
        i -= entriesToCluster - 1;
    }

    return clusteredChartData.reverse();
};

export const generateChartData = (histories: History[]): ChartData => {
    const chartData = histories
        .flatMap(generateChartDataFromSingleHistory)
        .sort((a, b) => a.queriedAt - b.queriedAt);

    if (chartData.length === 0) {
        return [];
    }

    const clusteredChartData = clusterChartData(chartData);

    // Merge duplicate queriedAt values
    const mergedChartData: ChartData = [clusteredChartData[0]];
    for (const entry of clusteredChartData) {
        const lastEntry = mergedChartData[mergedChartData.length - 1];
        if (lastEntry.queriedAt === entry.queriedAt) {
            mergedChartData[mergedChartData.length - 1] = {
                ...lastEntry,
                ...entry,
            };
        } else {
            mergedChartData.push(entry);
        }
    }
    return mergedChartData;
};
