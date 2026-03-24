import { Layout } from "#components/Layout.tsx";
import { createRootRouteWithContext, Outlet } from "@tanstack/react-router";
import type { RouterContext } from "#routerContext.ts";
import React, { Suspense } from "react";

const TanStackRouterDevtools = import.meta.env.PROD
    ? () => null // Render nothing in production
    : React.lazy(() =>
          // Lazy load in development
          import("@tanstack/react-router-devtools").then((res) => ({
              default: res.TanStackRouterDevtools,
          })),
      );

const ReactQueryDevtools = import.meta.env.PROD
    ? () => null // Render nothing in production
    : React.lazy(() =>
          // Lazy load in development
          import("@tanstack/react-query-devtools").then((res) => ({
              default: res.ReactQueryDevtools,
          })),
      );

const RouteComponent: React.FC = () => {
    return (
        <>
            <Layout>
                <Outlet />
            </Layout>
            <Suspense>
                <TanStackRouterDevtools />
                <ReactQueryDevtools initialIsOpen={false} />
            </Suspense>
        </>
    );
};

export const Route = createRootRouteWithContext<RouterContext>()({
    component: RouteComponent,
});
