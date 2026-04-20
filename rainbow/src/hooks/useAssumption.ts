import { captureMessage } from "@sentry/react";
import React from "react";

export function useAssume() {
    const assumptions = React.useRef<Record<string, boolean | undefined>>({});

    return React.useCallback(function assume(
        assumption: boolean,
        message: string,
        getMeta?: () => Record<string, unknown>,
    ) {
        if (assumption) {
            // Assumption holds -> continue
            return;
        }

        if (assumptions.current[message] === true) {
            // We've already reported this assumption failure
            return;
        }

        const meta = getMeta?.();

        captureMessage(`Assumption failed: ${message}`, {
            level: "error",
            extra: meta,
        });

        if (import.meta.env.DEV) {
            // oxlint-disable-next-line eslint/no-alert
            alert(`Assumption failed: ${message}\n\n${JSON.stringify(meta, null, 2)}`);
        }

        assumptions.current[message] = true;
    }, []);
}
