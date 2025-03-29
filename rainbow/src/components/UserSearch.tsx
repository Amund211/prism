import { getUUIDQueryOptions } from "#queries/uuid.ts";
import { isUUID } from "#helpers/uuid.ts";
import { useUUIDToUsername } from "#queries/username.ts";
import { Search } from "@mui/icons-material";
import {
    Autocomplete,
    AutocompleteProps,
    Avatar,
    CircularProgress,
    InputAdornment,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import { useQueryClient } from "@tanstack/react-query";
import React from "react";
import { getKnownAliases } from "#helpers/knownAliases.ts";

interface UserSearchProps {
    onSubmit: (uuid: string) => void;
    placeholder?: string;
    size?: "small" | "medium";
}

interface UserSearchOptions {
    uuids: string[];
    filterOptions: AutocompleteProps<
        string,
        false,
        true,
        true
    >["filterOptions"];
    renderOption: AutocompleteProps<string, false, true, true>["renderOption"];
    getOptionLabel: AutocompleteProps<
        string,
        false,
        true,
        true
    >["getOptionLabel"];
    isOptionEqualToValue: AutocompleteProps<
        string,
        false,
        true,
        true
    >["isOptionEqualToValue"];
}

const useUserSearchOptions = (): UserSearchOptions => {
    const knownAliases = getKnownAliases();
    const uuids = Object.keys(knownAliases);
    const uuidToUsername = useUUIDToUsername(uuids);

    return {
        uuids,
        filterOptions: (options, { inputValue }) => {
            if (inputValue === "") return options;
            const namesForOptions = options.map((option) => {
                const uuid = option;
                const name = uuidToUsername[uuid];
                const names = knownAliases[uuid] ?? [];
                if (!name) {
                    return {
                        names,
                        option,
                    };
                }
                return { names: [name, ...names], option };
            });

            return namesForOptions
                .filter(({ names }) => {
                    return names.some((name) =>
                        name.toLowerCase().includes(inputValue.toLowerCase()),
                    );
                })
                .map(({ option }) => option);
        },
        renderOption: (props, option) => {
            const { key, ...optionProps } = props; // eslint-disable-line @typescript-eslint/no-unsafe-assignment
            const uuid = option;
            return (
                <Stack
                    component="li"
                    key={key} // eslint-disable-line @typescript-eslint/no-unsafe-assignment
                    direction="row"
                    gap={2}
                    alignItems="center"
                    {...optionProps}
                >
                    <Avatar
                        // TODO: Attribution - https://crafatar.com/#meta-attribution
                        src={`https://crafatar.com/renders/head/${uuid}?overlay`}
                        alt={`Player head of ${uuidToUsername[uuid] ?? "unknown"}`}
                    />
                    <Typography variant="body1">
                        {uuidToUsername[uuid]}
                    </Typography>
                </Stack>
            );
        },
        getOptionLabel: (option) => {
            return uuidToUsername[option] ?? option;
        },
        isOptionEqualToValue: (option, value) => {
            return (
                option === value ||
                uuidToUsername[option]?.toLowerCase() === value.toLowerCase()
            );
        },
    };
};

export const UserSearch: React.FC<UserSearchProps> = ({
    onSubmit,
    placeholder = "Search players",
    size = "small",
}) => {
    const queryClient = useQueryClient();
    const {
        uuids,
        filterOptions,
        renderOption,
        getOptionLabel,
        isOptionEqualToValue,
    } = useUserSearchOptions();
    const [loading, setLoading] = React.useState(false);

    return (
        <Autocomplete
            freeSolo
            options={uuids}
            fullWidth
            size={size}
            // TODO: Clear the input when the user selects an option
            blurOnSelect
            selectOnFocus
            autoHighlight
            filterOptions={filterOptions}
            renderOption={renderOption}
            getOptionLabel={getOptionLabel}
            isOptionEqualToValue={isOptionEqualToValue}
            onChange={(_, value) => {
                if (!value) return; // Ignore clearing the input

                // Allow UUIDs to be entered directly
                if (isUUID(value)) {
                    onSubmit(value);
                    return;
                }

                setLoading(true);
                queryClient
                    .fetchQuery(getUUIDQueryOptions(value))
                    .then(({ uuid }) => {
                        onSubmit(uuid);
                    })
                    .catch((error: unknown) => {
                        console.error("Failed to fetch username", error);
                    })
                    .finally(() => {
                        setLoading(false);
                    });
            }}
            renderInput={(params) => {
                return (
                    <TextField
                        {...params}
                        placeholder={placeholder}
                        slotProps={{
                            input: {
                                ...params.InputProps,
                                startAdornment: (
                                    <InputAdornment position="start">
                                        {loading ? (
                                            <CircularProgress size={20} />
                                        ) : (
                                            <Search fontSize="small" />
                                        )}
                                    </InputAdornment>
                                ),
                            },
                        }}
                    />
                );
            }}
        />
    );
};
