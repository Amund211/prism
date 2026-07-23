import { getOrSetUserId } from "#helpers/userId.ts";

// Client identification headers consumed by the flashlight backend. rainbow is
// evergreen (always served from the latest deploy), so it always reports the
// "evergreen" version. See https://github.com/Amund211/flashlight/pull/328.
//
// IMPORTANT: These headers identify us to flashlight and must ONLY be sent to
// the flashlight API. Do not attach them to requests to any other server.
const CLIENT_TYPE = "rainbow";
const CLIENT_VERSION = "evergreen";

// getFlashlightHeaders returns the headers to send with every request to the
// flashlight API. Centralizing them here keeps the client identification
// consistent across call sites and ensures they are only sent to flashlight.
export const getFlashlightHeaders = (): Record<string, string> => ({
    "X-User-Id": getOrSetUserId(),
    "X-Client-Type": CLIENT_TYPE,
    "X-Client-Version": CLIENT_VERSION,
});
