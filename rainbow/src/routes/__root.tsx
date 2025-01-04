import { createRootRoute, Link, Outlet } from "@tanstack/react-router";
import React, { Suspense } from "react";

const TanStackRouterDevtools =
    import.meta.env.NODE_ENV === "production"
        ? () => null // Render nothing in production
        : React.lazy(() =>
              // Lazy load in development
              import("@tanstack/router-devtools").then((res) => ({
                  default: res.TanStackRouterDevtools,
              })),
          );

export const Route = createRootRoute({
    component: () => (
        <>
            <div>
                <Link to="/">Home</Link> <Link to="/about">About</Link>
            </div>
            <hr />
            <Outlet />
            <Suspense>
                <TanStackRouterDevtools />
            </Suspense>
        </>
    ),
});
