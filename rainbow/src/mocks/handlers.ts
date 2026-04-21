import { http, HttpResponse } from "msw";

import { isNormalizedUUID } from "#helpers/uuid.ts";
import type { APIPlayerDataPIT } from "#queries/playerdata.ts";
import type { APISession } from "#queries/sessions.ts";

import {
    findUserByUsername,
    findUserByUUID,
    makePlayerDataPIT,
    makeSession,
    makeWrappedResponse,
} from "./data.ts";

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
        const { username } = req.params;
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
    http.post(flashlightEndpoint("v1/history"), async ({ request }) => {
        const body = (await request.json()) as {
            uuid: string;
            start: string;
            end: string;
            limit: number;
        };
        validateUUID(body.uuid);

        const startDate = new Date(body.start);
        const endDate = new Date(body.end);

        if (body.limit <= 2) {
            // For limit=2: return start and end only
            const history: APIPlayerDataPIT[] = [
                makePlayerDataPIT(body.uuid, startDate.toISOString(), 1),
                makePlayerDataPIT(body.uuid, endDate.toISOString(), 3),
            ].slice(0, body.limit);
            return HttpResponse.json(history);
        }

        const midDate = new Date((startDate.getTime() + endDate.getTime()) / 2);

        const history: APIPlayerDataPIT[] = [
            makePlayerDataPIT(body.uuid, startDate.toISOString(), 1),
            makePlayerDataPIT(body.uuid, midDate.toISOString(), 2),
            makePlayerDataPIT(body.uuid, endDate.toISOString(), 3),
        ].slice(0, body.limit);

        return HttpResponse.json(history);
    }),
    http.post(flashlightEndpoint("v1/sessions"), async ({ request }) => {
        const body = (await request.json()) as {
            uuid: string;
            start: string;
            end: string;
        };
        validateUUID(body.uuid);

        const startDate = new Date(body.start);
        const endDate = new Date(body.end);
        const midDate = new Date((startDate.getTime() + endDate.getTime()) / 2);

        const sessions: APISession[] = [
            makeSession(body.uuid, startDate.toISOString(), midDate.toISOString()),
            makeSession(body.uuid, midDate.toISOString(), endDate.toISOString()),
        ];

        return HttpResponse.json(sessions);
    }),
    http.get(flashlightEndpoint("v1/wrapped/:uuid/:year"), (req) => {
        const uuid = validateUUID(req.params.uuid);
        const yearParam = req.params.year;
        if (typeof yearParam !== "string") {
            throw new Error("Invalid year parameter");
        }
        const year = Number.parseInt(yearParam, 10);
        if (!Number.isFinite(year) || year < 2000 || year > 3000) {
            throw new Error("Invalid year parameter");
        }

        return HttpResponse.json(makeWrappedResponse(uuid, year));
    }),
    http.get("https://api.mineatar.io/:variant/:uuid", (req) => {
        validateUUID(req.params.uuid);

        // Placeholder image
        const pngData =
            "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAAXNSR0IB2cksfwAAAARnQU1BAACxjwv8YQUAAAAgY0hSTQAAeiYAAICEAAD6AAAAgOgAAHUwAADqYAAAOpgAABdwnLpRPAAAAAlwSFlzAAAuIwAALiMBeKU/dgAAAAd0SU1FB+oDFRAONPh9NXIAAABDSURBVCjPY6xn+M9ACmBiIBHQU0MjQ0MjQwOmCjRxkm1gpGMoNTIw4lKELMWESwKXIEIDxDNY9SD7E93TJGsYimkJAA3UEZ+W43wuAAAAAElFTkSuQmCC";
        // oxlint-disable-next-line unicorn/prefer-code-point -- atob produces single-byte chars (0-255), charCodeAt is semantically correct for byte extraction
        const buffer = Uint8Array.from(atob(pngData), (c) => c.charCodeAt(0));

        return HttpResponse.arrayBuffer(buffer.buffer, {
            headers: { "Content-Type": "image/png" },
        });
    }),
];
