const startOfDay = (date: Date) => {
    const d = new Date(date);
    d.setHours(0, 0, 0, 0);
    return d;
};
const endOfDay = (date: Date) => {
    const d = new Date(date);
    d.setHours(23, 59, 59, 999);
    return d;
};
const startOfWeek = (date: Date) => {
    const weekDayIndexedByMonday = (date.getDay() + 6) % 7;
    const d = new Date(date);
    d.setDate(date.getDate() - weekDayIndexedByMonday);
    return startOfDay(d);
};
const endOfWeek = (date: Date) => {
    const weekDayIndexedByMonday = (date.getDay() + 6) % 7;
    const d = new Date(date);
    d.setDate(date.getDate() + (6 - weekDayIndexedByMonday));
    return endOfDay(d);
};
const startOfMonth = (date: Date) => {
    const d = new Date(date);
    d.setDate(1);
    return startOfDay(d);
};
const endOfMonth = (date: Date) => {
    const d = new Date(date);
    d.setMonth(d.getMonth() + 1);
    d.setDate(0);
    return endOfDay(d);
};

export const endOfLastDay = (date: Date) => {
    const d = new Date(date);
    d.setDate(d.getDate() - 1);
    return endOfDay(d);
};
export const endOfLastWeek = (date: Date) => {
    const d = endOfWeek(date);
    d.setDate(d.getDate() - 7);
    return d;
};
export const endOfLastMonth = (date: Date) => {
    const d = new Date(date);
    d.setMonth(d.getMonth() - 1);
    return endOfMonth(d);
};

/**
 * Returns the date that is `days` before the given date
 *
 * NOTE: days=1 returns the same date at the start of the day
 */
const daysBefore = (date: Date, days: number) => {
    const d = new Date(date);
    d.setDate(d.getDate() - (days - 1));
    return startOfDay(d);
};

const daysInCurrentMonth = (date: Date) => {
    const d = new Date(date);
    d.setMonth(d.getMonth() + 1);
    d.setDate(0);
    return d.getDate();
};

export interface TimeIntervalDefinition {
    type: "contained" | "until";
    // If missing -> today's date
    date?: Date;
}

export interface TimeInterval {
    start: Date;
    end: Date;
}

interface TimeIntervals {
    day: TimeInterval;
    week: TimeInterval;
    month: TimeInterval;
}

export const timeIntervalsFromDefinition = (
    definition: TimeIntervalDefinition & { date: Date },
): TimeIntervals => {
    if (definition.type === "contained") {
        const now = definition.date;
        return {
            day: {
                start: startOfDay(now),
                end: endOfDay(now),
            },
            week: {
                start: startOfWeek(now),
                end: endOfWeek(now),
            },
            month: {
                start: startOfMonth(now),
                end: endOfMonth(now),
            },
        };
    } else {
        const end = endOfDay(definition.date);

        // TODO: Consider static 30 vs days in month
        const daysInMonth = daysInCurrentMonth(end);
        return {
            day: { start: daysBefore(end, 1), end },
            week: { start: daysBefore(end, 7), end },
            month: { start: daysBefore(end, daysInMonth), end },
        };
    }
};
