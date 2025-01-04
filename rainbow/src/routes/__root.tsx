import { createRootRoute, Link, Outlet } from "@tanstack/react-router";
import React, { Suspense } from "react";

const TanStackRouterDevtools =
    process.env.NODE_ENV === "production"
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
            <div className="p-2 flex gap-2">
                <Link to="/" className="[&.active]:font-bold">
                    Home
                </Link>{" "}
                <Link to="/about" className="[&.active]:font-bold">
                    About
                </Link>
            </div>
            <hr />
            <Outlet />
            <Suspense>
                <TanStackRouterDevtools />
            </Suspense>
        </>
    ),
});
