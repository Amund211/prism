import { getUUIDQueryOptions, normalizeUUID } from "#queries/uuid.ts";
import { Search } from "@mui/icons-material";
import { CircularProgress, InputAdornment, OutlinedInput } from "@mui/material";
import { useQueryClient } from "@tanstack/react-query";
import React from "react";

interface UserSearchProps {
    onSubmit: (uuid: string) => void;
}

const isUUID = (value: string) => {
    try {
        normalizeUUID(value);
    } catch {
        return false;
    }
    return true;
};

export const UserSearch: React.FC<UserSearchProps> = ({ onSubmit }) => {
    const queryClient = useQueryClient();

    const [search, setSearch] = React.useState("");
    const [loading, setLoading] = React.useState(false);

    return (
        <OutlinedInput
            value={search}
            onChange={(event) => {
                setSearch(event.currentTarget.value);
            }}
            placeholder="Search user..."
            startAdornment={
                <InputAdornment position="start">
                    {loading ? (
                        <CircularProgress size={20} />
                    ) : (
                        <Search fontSize="small" />
                    )}
                </InputAdornment>
            }
            fullWidth
            size="small"
            onKeyDown={(event) => {
                if (event.key === "Enter") {
                    const value = event.currentTarget.value;

                    // Allow UUIDs to be entered directly
                    if (isUUID(value)) {
                        onSubmit(value);
                        setSearch("");
                        return;
                    }

                    setLoading(true);
                    queryClient
                        .fetchQuery(getUUIDQueryOptions(value))
                        .then(({ uuid }) => {
                            onSubmit(uuid);
                            setSearch("");
                        })
                        .catch((error: unknown) => {
                            console.error("Failed to fetch username", error);
                        })
                        .finally(() => {
                            setLoading(false);
                        });
                }
            }}
        />
    );
};
