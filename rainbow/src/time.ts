// Milliseconds per unit of time, so duration maths reads in named units instead
// of repeated `24 * 60 * 60 * 1000`-style literals.
export const MS_PER_MINUTE = 60_000;
export const MS_PER_HOUR = 60 * MS_PER_MINUTE;
export const MS_PER_DAY = 24 * MS_PER_HOUR;
