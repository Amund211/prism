import * as Sentry from "@sentry/react";

import { env } from "#env.ts";

if (env.VITE_SENTRY_DSN) {
    Sentry.init({
        dsn: env.VITE_SENTRY_DSN,
        sendDefaultPii: false,
    });
}
