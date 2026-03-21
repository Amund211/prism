import { describe, expect } from "vitest";
import { USERS } from "#mocks/data.ts";
import { mswTest } from "#test/msw-test.ts";
import { stringifyPlayerVisits } from "#contexts/PlayerVisits/helpers.ts";
import { renderAppRoute } from "#test/render.tsx";

/**
 * Render the real app route tree navigated to a specific URL.
 * Use this for components that depend on Route.useSearch/useParams/useLoaderDeps.
 */
// Render the real app at a given route
describe("Home page", () => {
    mswTest("renders player search input", async () => {
        const { screen } = await renderAppRoute("/");

        await expect.element(screen.getByRole("combobox")).toBeInTheDocument();
    });

    mswTest("contains meta description about Prism Overlay", async () => {
        await renderAppRoute("/");

        await expect
            .poll(() => {
                return document.querySelector('meta[content*="Prism Overlay"]');
            })
            .toBeInTheDocument();
    });

    mswTest("contains canonical link", async () => {
        await renderAppRoute("/");

        await expect
            .poll(() => {
                return document.querySelector(
                    'link[href="https://prismoverlay.com"]',
                );
            })
            .toBeInTheDocument();
    });

    describe("favorites", () => {
        const setPlayerVisited = (uuid: string) => {
            localStorage.setItem(
                "playerVisits",
                stringifyPlayerVisits({
                    [uuid]: {
                        visitedCount: 1,
                        lastVisited: new Date(),
                    },
                }),
            );
        };

        mswTest(
            "displays favorites when playerVisits are in localStorage",
            async () => {
                setPlayerVisited(USERS.player1.uuid);

                const { screen } = await renderAppRoute("/");

                await expect
                    .element(screen.getByText(USERS.player1.username))
                    .toBeInTheDocument();
            },
        );

        mswTest("clicking favorite navigates to session page", async () => {
            setPlayerVisited(USERS.player1.uuid);

            const { screen } = await renderAppRoute("/");

            const favorite = screen.getByText(USERS.player1.username);

            await expect.element(favorite).toBeInTheDocument();

            await favorite.click();

            await expect
                .poll(() => window.location.pathname)
                .toBe(`/session/${USERS.player1.uuid}`);

            const search = new URLSearchParams(window.location.search);
            expect(search.get("gamemode")).toBe("overall");
            expect(search.get("stat")).toBe("fkdr");
            expect(search.get("timeIntervalDefinition")).toBe(
                JSON.stringify({ type: "contained" }),
            );
            expect(search.get("variantSelection")).toBe("both");
            expect(search.get("sessionTableMode")).toBe("total");
            expect(search.get("showExtrapolatedSessions")).toBe("false");

            await expect
                .element(
                    screen.getByRole("heading", {
                        name: `${USERS.player1.username}'s session stats`,
                    }),
                )
                .toBeInTheDocument();
        });

        mswTest("renders delete button with correct aria-label", async () => {
            setPlayerVisited(USERS.player1.uuid);

            const { screen } = await renderAppRoute("/");

            await expect
                .element(
                    screen.getByLabelText(
                        `Remove ${USERS.player1.username} from favorites`,
                    ),
                )
                .toBeInTheDocument();
        });

        mswTest(
            "removes favorite from localStorage when delete button is clicked",
            async () => {
                setPlayerVisited(USERS.player1.uuid);

                const { screen } = await renderAppRoute("/");

                await expect
                    .element(screen.getByText(USERS.player1.username))
                    .toBeInTheDocument();

                const deleteButtonIcon = screen.getByLabelText(
                    `Remove ${USERS.player1.username} from favorites`,
                );

                await expect.element(deleteButtonIcon).toBeInTheDocument();
                await deleteButtonIcon.click();

                await expect
                    .element(screen.getByText(USERS.player1.username))
                    .not.toBeInTheDocument();
                await expect.element(deleteButtonIcon).not.toBeInTheDocument();

                const stored = localStorage.getItem("playerVisits");
                expect(stored).toStrictEqual("{}");
            },
        );
    });
});
