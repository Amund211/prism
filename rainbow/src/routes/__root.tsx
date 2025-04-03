import { Layout } from "#components/Layout.tsx";
import { createRootRoute, Outlet } from "@tanstack/react-router";
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

export const Route = createRootRoute({
    component: RouteComponent,
});
