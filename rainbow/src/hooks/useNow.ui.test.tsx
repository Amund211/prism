import { afterEach, describe, expect, test, vi } from "vitest";
import { renderHook } from "vitest-browser-react";

import { useNow } from "#hooks/useNow.ts";

describe(useNow, () => {
    afterEach(() => {
        vi.useRealTimers();
    });

    test.each([
        ["second", new Date(2026, 0, 31, 23, 59, 30)],
        ["minute", new Date(2026, 0, 31, 23, 59, 0)],
        ["hour", new Date(2026, 0, 31, 23, 0, 0)],
        ["day", new Date(2026, 0, 31, 0, 0, 0)],
        ["month", new Date(2026, 0, 1, 0, 0, 0)],
        ["year", new Date(2026, 0, 1, 0, 0, 0)],
    ] as const)("truncates to %s", async (precision, expected) => {
        vi.useFakeTimers({ now: new Date(2026, 0, 31, 23, 59, 30, 500) });

        const { result } = await renderHook(() => useNow(precision));

        expect(result.current).toStrictEqual(expected);
    });

    test("updates at the next boundary", async () => {
        vi.useFakeTimers({ now: new Date(2026, 0, 31, 23, 59, 30) });

        const { result } = await renderHook(() => useNow("day"));
        await vi.advanceTimersByTimeAsync(30_000);

        await expect
            .poll(() => result.current)
            .toStrictEqual(new Date(2026, 1, 1, 0, 0, 0));
    });

    test("catches up soon after the system sleeps", async () => {
        vi.useFakeTimers({ now: new Date(2026, 0, 15, 12, 0, 0) });

        const { result } = await renderHook(() => useNow("month"));
        // Sleep: the wall clock jumps, but pending timers do not advance
        vi.setSystemTime(new Date(2026, 1, 1, 0, 0, 30));
        await vi.advanceTimersByTimeAsync(60_000);

        await expect
            .poll(() => result.current)
            .toStrictEqual(new Date(2026, 1, 1, 0, 0, 0));
    });

    test("does not re-render before its value changes", async () => {
        vi.useFakeTimers({ now: new Date(2026, 0, 31, 12, 0, 0) });

        let renders = 0;
        const { result } = await renderHook(() => {
            renders++;
            return useNow("day");
        });
        const first = result.current;
        const rendersAfterMount = renders;

        // A finer subscriber keeps the timer ticking every second
        await renderHook(() => useNow("second"));
        await vi.advanceTimersByTimeAsync(60 * 60 * 1000);

        expect(result.current).toBe(first);
        expect(renders).toBe(rendersAfterMount);
    });

    test("a new subscriber reads the current time while coarser subscribers exist", async () => {
        vi.useFakeTimers({ now: new Date(2026, 0, 31, 23, 30, 0) });

        await renderHook(() => useNow("month"));
        vi.setSystemTime(new Date(2026, 1, 1, 0, 0, 30));

        const rendered: Date[] = [];
        await renderHook(() => {
            const now = useNow("day");
            rendered.push(now);
            return now;
        });

        expect(rendered[0]).toStrictEqual(new Date(2026, 1, 1, 0, 0, 0));
    });

    test("shares one value between subscribers", async () => {
        vi.useFakeTimers({ now: new Date(2026, 0, 31, 12, 0, 0) });

        const a = await renderHook(() => useNow("minute"));
        const b = await renderHook(() => useNow("minute"));

        expect(a.result.current).toBe(b.result.current);
    });

    test("stops the timer when the last subscriber unmounts", async () => {
        vi.useFakeTimers({ now: new Date(2026, 0, 31, 12, 0, 0) });

        const { unmount } = await renderHook(() => useNow("minute"));
        expect(vi.getTimerCount()).toBe(1);

        await unmount();

        expect(vi.getTimerCount()).toBe(0);
    });
});
