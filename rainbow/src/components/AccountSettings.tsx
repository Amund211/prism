import {
    Alert,
    Button,
    Dialog,
    DialogActions,
    DialogContent,
    DialogContentText,
    DialogTitle,
    List,
    ListItem,
    ListItemText,
    Stack,
    Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import React from "react";

import { startMicrosoftSignIn } from "#helpers/flashlight/auth/microsoft.ts";
import { signOutEverywhere } from "#helpers/flashlight/auth/session.ts";
import { useAuthSession } from "#helpers/flashlight/auth/useAuthSession.ts";
import { FlashlightResponseError } from "#helpers/flashlight/request.ts";
import {
    credentialsQueryKey,
    getCredentialsQueryOptions,
} from "#queries/credentials.ts";
import { getUsernameQueryOptions } from "#queries/username.ts";

const CLIENT_LABELS: ReadonlyMap<string, string> = new Map([
    ["rainbow", "Browser"],
    ["prism", "Prism overlay"],
]);

const formatDate = (iso: string): string =>
    new Date(iso).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
    });

const SignedInAs: React.FC<{ readonly uuid: string | undefined }> = ({ uuid }) => {
    const { data } = useQuery({
        ...getUsernameQueryOptions(uuid ?? ""),
        enabled: uuid !== undefined,
    });
    return (
        <Typography>
            {data === undefined
                ? "Signed in with Microsoft"
                : `Signed in as ${data.username}`}
        </Typography>
    );
};

const ActiveSignIns: React.FC<{ readonly uuid: string | undefined }> = ({ uuid }) => {
    const { data, error } = useQuery(getCredentialsQueryOptions(uuid));

    if (error instanceof FlashlightResponseError && error.status === 403) {
        // The session is not microsoft (another tab signed out). The section
        // switches to the anonymous view on the next storage event.
        return null;
    }
    if (error !== null) {
        return <Alert severity="error">Could not load your sign-ins.</Alert>;
    }
    if (data === undefined) {
        return null;
    }

    return (
        <Stack>
            <Typography variant="subtitle1">Active sign-ins</Typography>
            <List dense>
                {data.map((credential) => (
                    <ListItem key={`${credential.clientType}-${credential.createdAt}`}>
                        <ListItemText
                            primary={
                                CLIENT_LABELS.get(credential.clientType) ??
                                credential.clientType
                            }
                            secondary={`Signed in ${formatDate(credential.createdAt)} · last used ${formatDate(credential.lastUsedAt)}`}
                        />
                    </ListItem>
                ))}
            </List>
        </Stack>
    );
};

const SignOutEverywhere: React.FC = () => {
    const queryClient = useQueryClient();
    const [open, setOpen] = React.useState(false);
    const mutation = useMutation({
        mutationFn: signOutEverywhere,
        onSuccess: () => {
            queryClient.removeQueries({ queryKey: credentialsQueryKey });
        },
        onSettled: () => {
            setOpen(false);
        },
    });

    return (
        <>
            {mutation.isError && (
                <Alert severity="error">Could not sign out. Try again.</Alert>
            )}
            <Button
                variant="outlined"
                color="error"
                sx={{ alignSelf: "flex-start" }}
                onClick={() => {
                    setOpen(true);
                }}
            >
                Sign out everywhere
            </Button>
            <Dialog
                open={open}
                onClose={() => {
                    // Closing cannot stop a sign-out that has started.
                    if (!mutation.isPending) {
                        setOpen(false);
                    }
                }}
            >
                <DialogTitle>Sign out everywhere?</DialogTitle>
                <DialogContent>
                    <DialogContentText>
                        This also signs out every Prism overlay and browser for this
                        account.
                    </DialogContentText>
                </DialogContent>
                <DialogActions>
                    <Button
                        disabled={mutation.isPending}
                        onClick={() => {
                            setOpen(false);
                        }}
                    >
                        Cancel
                    </Button>
                    <Button
                        color="error"
                        loading={mutation.isPending}
                        onClick={() => {
                            mutation.mutate();
                        }}
                    >
                        Sign out
                    </Button>
                </DialogActions>
            </Dialog>
        </>
    );
};

/**
 * The settings "Account" section: Microsoft sign-in, the active sign-ins and
 * sign out everywhere.
 */
export const AccountSettings: React.FC = () => {
    const session = useAuthSession();
    // Throws only if the verifier cannot be stored. On success the page leaves.
    const signIn = useMutation({ mutationFn: startMicrosoftSignIn });

    return (
        <Stack sx={{ gap: 1 }}>
            <Typography variant="h6">Account</Typography>
            {session?.tier === "microsoft" ? (
                <>
                    <SignedInAs uuid={session.uuid} />
                    <ActiveSignIns uuid={session.uuid} />
                    <SignOutEverywhere />
                </>
            ) : (
                <>
                    <Typography>
                        Sign in to get your own request quota instead of sharing one.
                    </Typography>
                    {signIn.isError && (
                        <Alert severity="error">
                            Could not start the sign-in. Try again.
                        </Alert>
                    )}
                    <Button
                        variant="contained"
                        sx={{ alignSelf: "flex-start" }}
                        onClick={() => {
                            signIn.mutate();
                        }}
                    >
                        Sign in with Microsoft
                    </Button>
                </>
            )}
        </Stack>
    );
};
