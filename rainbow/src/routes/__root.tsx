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
                <Link
                    to="/history/compare"
                    search={{
                        uuids: [
                            "a937646b-f115-44c3-8dbf-9ae4a65669a0", // Skydeath
                            "ac04f297-f74c-44de-a24e-0083936ac59a", // USBB
                            "062c373b-28de-4ec0-ab2c-0114e59e36ce", // Skydeaf
                            "3d58a2de-3831-4a17-a305-67258295f81e", // iCiara
                            "6bc1dd0f-f351-4c3d-b6cc-262e55b6e7aa", // HardcoreLizard
                        ],
                        start: new Date("2025-01-15T19:55:00+01:00"),
                        end: new Date("2025-01-15T22:30:00+01:00"),
                        limit: 100,
                        stats: ["stars", "finalKills"],
                        gamemodes: ["overall"],
                        variants: ["session"],
                    }}
                >
                    Compare
                </Link>{" "}
                <Link
                    to="/session"
                    search={{
                        uuid: "a937646b-f115-44c3-8dbf-9ae4a65669a0",
                        timeInterval: {
                            type: "lastXDays",
                            end: new Date("2025-01-15T22:30:00+01:00"),
                        },
                    }}
                >
                    Session
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
