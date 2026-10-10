import { Button, CircularProgress, Stack, Typography } from "@mui/material";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import React from "react";

import { useCurrentUser } from "#contexts/CurrentUser/hooks.ts";
import {
    finishMicrosoftSignIn,
    startMicrosoftSignIn,
} from "#helpers/flashlight/auth/microsoft.ts";

const START_FAILED_MESSAGE = "Could not start the sign-in. Try again later.";

function RouteComponent() {
    const navigate = useNavigate();
    const { currentUser, setCurrentUser } = useCurrentUser();
    const [failure, setFailure] = React.useState<{
        readonly message: string;
        readonly retryable: boolean;
    } | null>(null);

    const retry = async () => {
        try {
            await startMicrosoftSignIn();
        } catch {
            setFailure({ message: START_FAILED_MESSAGE, retryable: true });
        }
    };

    const onSignedIn = React.useEffectEvent(async (uuid: string | undefined) => {
        if (currentUser === null && uuid !== undefined) {
            setCurrentUser(uuid);
        }
        await navigate({ to: "/settings", replace: true });
    });

    React.useEffect(() => {
        let cancelled = false;
        const finish = async () => {
            const outcome = await finishMicrosoftSignIn();
            if (cancelled) {
                return;
            }
            if (outcome.kind === "failed") {
                setFailure(outcome);
                return;
            }
            await onSignedIn(outcome.session.uuid);
        };
        void finish();
        return () => {
            cancelled = true;
        };
    }, []);

    return (
        <Stack sx={{ gap: 2, alignItems: "center", paddingTop: 4 }}>
            <meta name="robots" content="noindex" />
            {failure === null ? (
                <>
                    <CircularProgress />
                    <Typography variant="body1">Signing in…</Typography>
                </>
            ) : (
                <>
                    <Typography variant="body1">{failure.message}</Typography>
                    {failure.retryable && (
                        <Button
                            variant="contained"
                            onClick={() => {
                                void retry();
                            }}
                        >
                            Try again
                        </Button>
                    )}
                </>
            )}
        </Stack>
    );
}

export const Route = createFileRoute("/auth/microsoft")({
    component: RouteComponent,
});
