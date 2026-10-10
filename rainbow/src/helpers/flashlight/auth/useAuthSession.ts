import React from "react";

import { getSessionSnapshot, subscribeSession } from "./storage.ts";
import type { Session } from "./storage.ts";

/**
 * The stored session, updated on every write or clear, in this tab or another.
 */
export const useAuthSession = (): Session | null =>
    React.useSyncExternalStore(subscribeSession, getSessionSnapshot);
