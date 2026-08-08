import { beforeEach } from "vitest";

beforeEach(() => {
    // Ensure localstorage doesn't leak between tests. NOTE: this drops the auth
    // session too, so every test does a (mocked) anonymous login before its
    // first query.
    localStorage.clear();
});
