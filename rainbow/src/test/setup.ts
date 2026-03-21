import { beforeEach } from "vitest";

beforeEach(() => {
    // Ensure localstorage doesn't leak between tests
    localStorage.clear();
});
