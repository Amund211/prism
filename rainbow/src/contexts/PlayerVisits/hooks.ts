import React from "react";

import { PlayerVisitsContext } from "./context.ts";
import type { PlayerVisitsContextValue } from "./context.ts";

export const usePlayerVisits = (): PlayerVisitsContextValue => {
    const value = React.use(PlayerVisitsContext);
    if (value === null) {
        throw new Error("usePlayerVisits must be used within a PlayerVisitsProvider");
    }
    return value;
};
