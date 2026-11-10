import React from "react";

import { nextBoundary, truncate } from "#helpers/clock.ts";
import type { Precision } from "#helpers/clock.ts";
import { MS_PER_MINUTE } from "#time.ts";

const PRECISIONS_FINEST_FIRST = [
    "second",
    "minute",
    "hour",
    "day",
    "month",
    "year",
] as const;

// Timers pause while the system sleeps, and no event fires on wake
const MAX_DELAY_MS = MS_PER_MINUTE;
// Guards against a hot loop if a boundary is ever computed in the past
const MIN_DELAY_MS = 50;

const perPrecision = <T>(make: (p: Precision) => T) =>
    Object.fromEntries(PRECISIONS_FINEST_FIRST.map((p) => [p, make(p)])) as Record<
        Precision,
        T
    >;

const initMs = Date.now();
const snapshots = perPrecision((p) => new Date(truncate(initMs, p)));
const listeners = perPrecision(() => new Set<() => void>());
let timer: ReturnType<typeof setTimeout> | undefined;

// Unchanged snapshots keep their identity, so their subscribers skip re-rendering
const refreshPrecision = (p: Precision, ms: number): boolean => {
    const truncated = truncate(ms, p);
    if (truncated === snapshots[p].getTime()) {
        return false;
    }
    snapshots[p] = new Date(truncated);
    return true;
};

const finestSubscribed = () =>
    PRECISIONS_FINEST_FIRST.find((p) => listeners[p].size > 0);

const tick = () => {
    const ms = Date.now();
    for (const p of PRECISIONS_FINEST_FIRST) {
        if (refreshPrecision(p, ms)) {
            for (const listener of listeners[p]) {
                listener();
            }
        }
    }

    clearTimeout(timer);
    timer = undefined;
    const finest = finestSubscribed();
    if (finest === undefined) {
        return;
    }
    const now = Date.now();
    const delay = nextBoundary(now, finest) - now;
    timer = setTimeout(tick, Math.min(Math.max(delay, MIN_DELAY_MS), MAX_DELAY_MS));
};

// Timers are throttled in hidden tabs; catch up when the tab is shown again
const onVisibilityChange = () => {
    if (!document.hidden) {
        tick();
    }
};

const makeSubscribe = (precision: Precision) => (listener: () => void) => {
    const finestBefore = finestSubscribed();
    listeners[precision].add(listener);
    if (finestBefore === undefined) {
        document.addEventListener("visibilitychange", onVisibilityChange);
    }
    if (finestSubscribed() !== finestBefore) {
        tick();
    }

    return () => {
        const finestBeforeUnsubscribe = finestSubscribed();
        listeners[precision].delete(listener);
        const finest = finestSubscribed();
        if (finest === undefined) {
            document.removeEventListener("visibilitychange", onVisibilityChange);
        }
        if (finest !== finestBeforeUnsubscribe) {
            tick();
        }
    };
};

const subscribers = perPrecision(makeSubscribe);

const getSnapshots = perPrecision((p) => () => {
    // The timer keeps only subscribed precisions fresh
    if (listeners[p].size === 0) {
        refreshPrecision(p, Date.now());
    }
    return snapshots[p];
});

/**
 * The current local time, truncated to `precision`.
 * All callers share one clock. A caller re-renders only when its truncated value changes.
 */
export function useNow(precision: Precision): Date {
    return React.useSyncExternalStore(subscribers[precision], getSnapshots[precision]);
}
