import { http, HttpResponse } from "msw/http";
import { describe, expect } from "vitest";

import { makePNG } from "#helpers/uploadTestData.ts";
import { MOCK_STORAGE_URL, MOCK_UPLOAD_ID } from "#mocks/handlers.ts";
import { mswTest } from "#test/msw-test.ts";
import { renderAppRoute } from "#test/render.tsx";

const endpoint = (path: string) => `http://localhost:5173/flashlight/${path}`;

const png = (name: string, width = 1920, height = 1080, colorType = 6) =>
    new File([makePNG(width, height, colorType)], name, { type: "image/png" });

type Screen = Awaited<ReturnType<typeof renderAppRoute>>["screen"];

const fillRequiredFields = async (screen: Screen) => {
    await screen.getByLabelText("Launcher", { exact: true }).selectOptions("lunar");
    await screen.getByLabelText("Minecraft version").selectOptions("1.8.9");
    await screen.getByLabelText("Resource pack (optional)").fill("Default");
    await screen.getByLabelText("GUI scale (optional)").selectOptions("auto");
    await screen.getByRole("checkbox", { name: /I agree/ }).click();
};

describe("Tabcap upload page", () => {
    mswTest("submit is disabled until the form is complete", async () => {
        const { screen } = await renderAppRoute("/contribute/tabcap");

        const submit = screen.getByRole("button", { name: "Upload" });
        await expect.element(submit).toBeDisabled();

        // A disabled button takes no pointer events; the hover reaches its wrapper.
        await submit.hover({ force: true });
        await expect
            .element(screen.getByRole("tooltip"))
            .toHaveTextContent("Add at least one screenshot.");

        await screen.getByLabelText("Choose screenshots").upload([png("a.png")]);
        await expect.element(submit).toBeDisabled();
        await submit.hover({ force: true });
        await expect
            .element(screen.getByRole("tooltip"))
            .toHaveTextContent("Choose your launcher.");

        await fillRequiredFields(screen);
        await expect.element(submit).toBeEnabled();
    });

    mswTest(
        "starts the upload, posts each file to storage, then completes",
        async ({ worker }) => {
            const started: { body: unknown; authorization: string | null }[] = [];
            const posted: {
                keys: string[];
                fieldOrder: string[];
                file: string;
                authorization: string | null;
            }[] = [];
            const completed: { url: string; authorization: string | null }[] = [];
            worker.use(
                http.post(endpoint("v1/uploads/:kind"), async ({ request }) => {
                    const body = (await request.json()) as {
                        files: readonly unknown[];
                    };
                    started.push({
                        body,
                        authorization: request.headers.get("Authorization"),
                    });
                    return HttpResponse.json(
                        {
                            success: true,
                            uploadId: MOCK_UPLOAD_ID,
                            expiresAt: "2026-11-07T21:45:00Z",
                            files: body.files.map((_, index) => ({
                                url: MOCK_STORAGE_URL,
                                fields: {
                                    key: `pending/${index.toString()}.png`,
                                    policy: "signed",
                                },
                            })),
                        },
                        { status: 201 },
                    );
                }),
                http.post(MOCK_STORAGE_URL, async ({ request }) => {
                    const form = await request.formData();
                    posted.push({
                        keys: form.getAll("key") as string[],
                        fieldOrder: [...form.keys()],
                        file: (form.get("file") as File).name,
                        authorization: request.headers.get("Authorization"),
                    });
                    return new HttpResponse(null, { status: 204 });
                }),
                http.post(
                    endpoint("v1/uploads/:kind/:uploadId/complete"),
                    ({ request, params }) => {
                        completed.push({
                            url: new URL(request.url).pathname,
                            authorization: request.headers.get("Authorization"),
                        });
                        return HttpResponse.json({
                            success: true,
                            uploadId: params.uploadId,
                        });
                    },
                ),
            );

            const { screen } = await renderAppRoute("/contribute/tabcap");

            const a = png("a.png");
            const b = png("b.png", 2560, 1440, 2);
            await screen.getByLabelText("Choose screenshots").upload([a, b]);
            await fillRequiredFields(screen);
            await screen.getByLabelText("Discord name (optional)").fill("someone");
            await screen.getByRole("button", { name: "Upload" }).click();

            await expect.element(screen.getByText("Thank you!")).toBeInTheDocument();
            await expect
                .element(screen.getByText(new RegExp(MOCK_UPLOAD_ID)))
                .toBeInTheDocument();

            expect(started).toHaveLength(1);
            expect(started[0]?.authorization).toMatch(/^Bearer /);
            expect(started[0]?.body).toStrictEqual({
                consentVersion: "2026-11-07",
                fields: {
                    launcher: "lunar",
                    mcVersion: "1.8.9",
                    resourcePack: "Default",
                    guiScale: "auto",
                    contact: "someone",
                },
                files: [
                    { name: "a.png", bytes: a.size },
                    { name: "b.png", bytes: b.size },
                ],
            });

            // Files are posted in parallel, so in any order.
            expect(
                posted
                    .map((post) => [post.keys[0] ?? "", post.file])
                    .toSorted(([x = ""], [y = ""]) => x.localeCompare(y)),
            ).toStrictEqual([
                ["pending/0.png", "a.png"],
                ["pending/1.png", "b.png"],
            ]);
            for (const post of posted) {
                expect(post.authorization).toBeNull();
                expect(post.fieldOrder.at(-1)).toBe("file");
            }

            expect(completed).toStrictEqual([
                {
                    url: `/flashlight/v1/uploads/tabcap/${MOCK_UPLOAD_ID}/complete`,
                    authorization: expect.stringMatching(/^Bearer /) as unknown,
                },
            ]);
        },
    );

    mswTest("resource pack and GUI scale are optional", async ({ worker }) => {
        let fields: unknown = null;
        worker.use(
            http.post(endpoint("v1/uploads/:kind"), async ({ request }) => {
                ({ fields } = (await request.json()) as { fields: unknown });
                return HttpResponse.json(
                    { success: false, cause: "stop" },
                    { status: 400 },
                );
            }),
        );

        const { screen } = await renderAppRoute("/contribute/tabcap");

        await screen.getByLabelText("Choose screenshots").upload([png("a.png")]);
        await screen.getByLabelText("Launcher", { exact: true }).selectOptions("lunar");
        await screen.getByLabelText("Minecraft version").selectOptions("1.8.9");
        // A chosen GUI scale can be unset again.
        await screen.getByLabelText("GUI scale (optional)").selectOptions("2");
        await screen.getByLabelText("GUI scale (optional)").selectOptions("Not set");
        await screen.getByRole("checkbox", { name: /I agree/ }).click();
        await screen.getByRole("button", { name: "Upload" }).click();

        await expect.element(screen.getByText("stop")).toBeInTheDocument();
        expect(fields).toStrictEqual({ launcher: "lunar", mcVersion: "1.8.9" });
    });

    mswTest("files cannot be added while the upload runs", async ({ worker }) => {
        let release: (() => void) | undefined;
        // oxlint-disable-next-line promise/avoid-new
        const held = new Promise<void>((resolve) => {
            release = resolve;
        });
        worker.use(
            http.post(endpoint("v1/uploads/:kind"), async () => {
                await held;
                return HttpResponse.json(
                    { success: false, cause: "stop" },
                    { status: 400 },
                );
            }),
        );

        const { screen } = await renderAppRoute("/contribute/tabcap");

        const picker = screen.getByLabelText("Choose screenshots");
        await picker.upload([png("a.png")]);
        await fillRequiredFields(screen);
        await screen.getByRole("button", { name: "Upload" }).click();

        await expect.element(picker).toBeDisabled();
        release?.();
        await expect.element(screen.getByText("stop")).toBeInTheDocument();
        await expect.element(picker).toBeEnabled();
    });

    mswTest("a start response with too few targets fails", async ({ worker }) => {
        let completeCalls = 0;
        worker.use(
            http.post(endpoint("v1/uploads/:kind"), () =>
                HttpResponse.json(
                    {
                        success: true,
                        uploadId: MOCK_UPLOAD_ID,
                        expiresAt: "2026-11-07T21:45:00Z",
                        files: [],
                    },
                    { status: 201 },
                ),
            ),
            http.post(endpoint("v1/uploads/:kind/:uploadId/complete"), () => {
                completeCalls += 1;
                return HttpResponse.json({ success: true, uploadId: MOCK_UPLOAD_ID });
            }),
        );

        const { screen } = await renderAppRoute("/contribute/tabcap");

        await screen.getByLabelText("Choose screenshots").upload([png("a.png")]);
        await fillRequiredFields(screen);
        await screen.getByRole("button", { name: "Upload" }).click();

        await expect
            .element(
                screen.getByText("Upload failed. Check your connection and try again."),
            )
            .toBeInTheDocument();
        expect(completeCalls).toBe(0);
    });

    mswTest("other launcher needs a name", async () => {
        const { screen } = await renderAppRoute("/contribute/tabcap");

        await screen.getByLabelText("Choose screenshots").upload([png("a.png")]);
        await fillRequiredFields(screen);
        await screen.getByLabelText("Launcher", { exact: true }).selectOptions("other");

        const submit = screen.getByRole("button", { name: "Upload" });
        await expect.element(submit).toBeDisabled();

        await screen.getByLabelText("Name of your launcher").fill("TLauncher");
        await expect.element(submit).toBeEnabled();
    });

    mswTest("a file that is not a PNG blocks the upload", async () => {
        const { screen } = await renderAppRoute("/contribute/tabcap");

        await screen
            .getByLabelText("Choose screenshots")
            .upload([new File(["not a png at all, no"], "photo.jpg")]);
        await fillRequiredFields(screen);

        await expect.element(screen.getByText("Not a PNG file")).toBeInTheDocument();
        await expect
            .element(screen.getByRole("button", { name: "Upload" }))
            .toBeDisabled();

        await screen.getByRole("button", { name: "Remove photo.jpg" }).click();
        await expect
            .element(screen.getByText("Not a PNG file"))
            .not.toBeInTheDocument();
    });

    mswTest("shows why the upload is not complete", async ({ worker }) => {
        worker.use(
            http.post(endpoint("v1/uploads/:kind/:uploadId/complete"), () =>
                HttpResponse.json(
                    {
                        success: false,
                        cause: "a.png: upload is not complete: file changed during the check",
                    },
                    { status: 409 },
                ),
            ),
        );

        const { screen } = await renderAppRoute("/contribute/tabcap");

        await screen.getByLabelText("Choose screenshots").upload([png("a.png")]);
        await fillRequiredFields(screen);
        await screen.getByRole("button", { name: "Upload" }).click();

        await expect
            .element(
                screen.getByText(
                    "a.png: upload is not complete: file changed during the check",
                ),
            )
            .toBeInTheDocument();
    });

    mswTest("shows why the server rejected the upload", async ({ worker }) => {
        worker.use(
            http.post(endpoint("v1/uploads/:kind/:uploadId/complete"), () =>
                HttpResponse.json(
                    {
                        success: false,
                        cause: "a.png: invalid upload: file is not a PNG",
                    },
                    { status: 400 },
                ),
            ),
        );

        const { screen } = await renderAppRoute("/contribute/tabcap");

        await screen.getByLabelText("Choose screenshots").upload([png("a.png")]);
        await fillRequiredFields(screen);
        await screen.getByRole("button", { name: "Upload" }).click();

        await expect
            .element(screen.getByText("a.png: invalid upload: file is not a PNG"))
            .toBeInTheDocument();
        await expect
            .element(screen.getByRole("button", { name: "Try again" }))
            .toBeEnabled();
    });

    mswTest("a file that storage refuses is named", async ({ worker }) => {
        let completeCalls = 0;
        worker.use(
            http.post(
                MOCK_STORAGE_URL,
                () => new HttpResponse("policy", { status: 400 }),
            ),
            http.post(endpoint("v1/uploads/:kind/:uploadId/complete"), () => {
                completeCalls += 1;
                return HttpResponse.json({ success: true, uploadId: MOCK_UPLOAD_ID });
            }),
        );

        const { screen } = await renderAppRoute("/contribute/tabcap");

        await screen.getByLabelText("Choose screenshots").upload([png("a.png")]);
        await fillRequiredFields(screen);
        await screen.getByRole("button", { name: "Upload" }).click();

        await expect
            .element(
                screen.getByText("a.png was not accepted. Remove it or try again."),
            )
            .toBeInTheDocument();
        expect(completeCalls).toBe(0);
    });
});
