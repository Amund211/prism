import { startOfDay, startOfMonth, startOfYear } from "#intervals.ts";
import { MS_PER_HOUR, MS_PER_MINUTE } from "#time.ts";

/** The unit the current time is truncated to. */
export type Precision = "second" | "minute" | "hour" | "day" | "month" | "year";

const SUB_DAY_MS = {
    second: 1000,
    minute: MS_PER_MINUTE,
    hour: MS_PER_HOUR,
} as const;

// Local-time setters resolve a repeated DST hour to its first occurrence, so
// sub-day units are cut with arithmetic on the instant's own offset instead
const truncateSubDay = (ms: number, unit: number): number => {
    const local = ms - new Date(ms).getTimezoneOffset() * MS_PER_MINUTE;
    return ms - (((local % unit) + unit) % unit);
};

/** The start (ms) of the local `precision` unit that contains `ms`. */
export const truncate = (ms: number, precision: Precision): number => {
    switch (precision) {
        case "year": {
            return startOfYear(new Date(ms)).getTime();
        }
        case "month": {
            return startOfMonth(new Date(ms)).getTime();
        }
        case "day": {
            return startOfDay(new Date(ms)).getTime();
        }
        case "hour":
        case "minute":
        case "second": {
            return truncateSubDay(ms, SUB_DAY_MS[precision]);
        }
    }
};

/** The start (ms) of the local `precision` unit after the one that contains `ms`. */
export const nextBoundary = (ms: number, precision: Precision): number => {
    const date = new Date(ms);
    switch (precision) {
        case "year": {
            return new Date(date.getFullYear() + 1, 0, 1).getTime();
        }
        case "month": {
            return new Date(date.getFullYear(), date.getMonth() + 1, 1).getTime();
        }
        // Built from the date, not from today's start, which may be a skipped 01:00
        case "day": {
            return new Date(
                date.getFullYear(),
                date.getMonth(),
                date.getDate() + 1,
            ).getTime();
        }
        case "hour":
        case "minute":
        case "second": {
            const unit = SUB_DAY_MS[precision];
            return truncateSubDay(ms, unit) + unit;
        }
    }
};
