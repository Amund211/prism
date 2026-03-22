import { http, HttpResponse } from "msw";
import { isNormalizedUUID } from "#helpers/uuid.ts";
import { findUserByUsername, findUserByUUID } from "./data.ts";

const flashlightEndpoint = (endpoint: string) => {
    if (endpoint.startsWith("/")) {
        throw new Error("Endpoint should not start with a slash");
    }
    return `http://localhost:5173/flashlight/${endpoint}`;
};

const validateUUID = (uuid: unknown): string => {
    if (typeof uuid !== "string") {
        throw new Error("Invalid UUID parameter");
    }

    if (!isNormalizedUUID(uuid)) {
        throw new Error("Invalid UUID format");
    }

    return uuid;
};

export const handlers = [
    http.get(flashlightEndpoint("v1/account/uuid/:uuid"), (req) => {
        const uuid = validateUUID(req.params.uuid);

        const user = findUserByUUID(uuid);
        if (user === null) {
            return HttpResponse.json(
                {
                    success: false,
                    uuid,
                    cause: "not found",
                },
                { status: 404 },
            );
        }

        return HttpResponse.json({
            success: true,
            username: user.username,
            uuid: user.uuid,
        });
    }),
    http.get(flashlightEndpoint("v1/account/username/:username"), (req) => {
        const username = req.params.username;
        if (typeof username !== "string" || username.length === 0) {
            throw new Error("Invalid username parameter");
        }

        const user = findUserByUsername(username);
        if (user === null) {
            return HttpResponse.json(
                {
                    success: false,
                    username,
                    cause: "not found",
                },
                { status: 404 },
            );
        }

        return HttpResponse.json({
            success: true,
            username: user.username,
            uuid: user.uuid,
        });
    }),
    http.get("https://api.mineatar.io/head/:uuid", (req) => {
        validateUUID(req.params.uuid);

        // Placeholder image
        const pngData =
            "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAAXNSR0IB2cksfwAAAARnQU1BAACxjwv8YQUAAAAgY0hSTQAAeiYAAICEAAD6AAAAgOgAAHUwAADqYAAAOpgAABdwnLpRPAAAAAlwSFlzAAAuIwAALiMBeKU/dgAAAAd0SU1FB+oDFRAONPh9NXIAAABDSURBVCjPY6xn+M9ACmBiIBHQU0MjQ0MjQwOmCjRxkm1gpGMoNTIw4lKELMWESwKXIEIDxDNY9SD7E93TJGsYimkJAA3UEZ+W43wuAAAAAElFTkSuQmCC";
        const buffer = Uint8Array.from(atob(pngData), (c) => c.charCodeAt(0));

        return HttpResponse.arrayBuffer(buffer.buffer, {
            headers: { "Content-Type": "image/png" },
        });
    }),
];
