import { MS_PER_MINUTE } from "#time.ts";

/**
 * Format a duration given in milliseconds as a short human-readable string.
 *
 * - Rolls over to days past 24h (`1d 1h`), dropping minutes at that scale.
 * - Rounds to the nearest minute and clamps negative inputs to `0m`.
 * - Zero-pads the minutes when hours are shown so values line up in a column.
 *
 * Callers with a start/end pair pass the difference, e.g.
 * `formatDuration(end.getTime() - start.getTime())`.
 */
export const formatDuration = (ms: number): string => {
    const totalMin = Math.max(0, Math.round(ms / MS_PER_MINUTE));
    const days = Math.floor(totalMin / (60 * 24));
    const hours = Math.floor((totalMin % (60 * 24)) / 60);
    const mins = totalMin % 60;
    if (days > 0) return `${days.toString()}d ${hours.toString()}h`;
    if (hours > 0) return `${hours.toString()}h ${mins.toString().padStart(2, "0")}m`;
    return `${mins.toString()}m`;
};
