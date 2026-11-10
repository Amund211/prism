// oxlint-disable-next-line import/no-namespace
import * as Sentry from "@sentry/react";

import { env } from "#env.ts";
import { redactHandles } from "#helpers/flashlight/request.ts";

const redactURL = (url: unknown): unknown =>
    typeof url === "string" ? redactHandles(url) : url;

/**
 * Remove the Microsoft result token from navigation breadcrumbs.
 */
export const redactBreadcrumb = (
    // Breadcrumb data is a mutable Record of unknowns, and cannot be made readonly
    // oxlint-disable-next-line typescript/prefer-readonly-parameter-types
    breadcrumb: Sentry.Breadcrumb,
): Sentry.Breadcrumb => {
    if (breadcrumb.category !== "navigation" || breadcrumb.data === undefined) {
        return breadcrumb;
    }
    return {
        ...breadcrumb,
        data: {
            ...breadcrumb.data,
            from: redactURL(breadcrumb.data.from),
            to: redactURL(breadcrumb.data.to),
        },
    };
};

/**
 * Remove the Microsoft result token from the event's page URL. Events sent
 * before the callback page removes its fragment carry it.
 */
export const redactEvent = <T extends Sentry.Event>(event: T): T =>
    event.request?.url === undefined
        ? event
        : {
              ...event,
              request: { ...event.request, url: redactHandles(event.request.url) },
          };

if (env.VITE_SENTRY_DSN !== undefined && env.VITE_SENTRY_DSN !== "") {
    Sentry.init({
        dsn: env.VITE_SENTRY_DSN,
        dataCollection: {
            userInfo: false,
        },
        beforeBreadcrumb: redactBreadcrumb,
        beforeSend: redactEvent,
    });
}
