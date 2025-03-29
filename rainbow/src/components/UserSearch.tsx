import { getUUIDQueryOptions } from "#queries/uuid.ts";
import { isUUID } from "#helpers/uuid.ts";
import { useUUIDToUsername } from "#queries/username.ts";
import { Search } from "@mui/icons-material";
import {
    Autocomplete,
    AutocompleteProps,
    Avatar,
    Chip,
    CircularProgress,
    InputAdornment,
    Skeleton,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import { useQueryClient } from "@tanstack/react-query";
import React from "react";
import { getKnownAliases } from "#helpers/knownAliases.ts";
import { orderUUIDsByScore } from "#helpers/favoritePlayers.ts";

interface UserSearchProps {
    onSubmit: (uuid: string) => void;
    placeholder?: string;
    size?: "small" | "medium";
}

interface UserSearchOptions<Multiple extends boolean> {
    uuids: string[];
    filterOptions: AutocompleteProps<
        string,
        Multiple,
        true,
        true
    >["filterOptions"];
    renderOption: AutocompleteProps<
        string,
        Multiple,
        true,
        true
    >["renderOption"];
    getOptionLabel: AutocompleteProps<
        string,
        false,
        true,
        true
    >["getOptionLabel"];
    isOptionEqualToValue: AutocompleteProps<
        string,
        Multiple,
        true,
        true
    >["isOptionEqualToValue"];
    renderTags: AutocompleteProps<string, Multiple, true, true>["renderTags"];
}

const useUserSearchOptions = <Multiple extends boolean = false>(
    additionalUUIDs?: readonly string[],
): UserSearchOptions<Multiple> => {
    const knownAliases = getKnownAliases();
    const uuids = Object.keys(knownAliases);
    const uuidToUsername = useUUIDToUsername(
        uuids.concat(additionalUUIDs ?? []),
    );

    return {
        uuids,
        filterOptions: (options, { inputValue }) => {
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

            return orderUUIDsByScore(
                namesForOptions
                    .filter(({ names }) => {
                        return names.some((name) =>
                            name
                                .toLowerCase()
                                .includes(inputValue.toLowerCase()),
                        );
                    })
                    .map(({ option }) => option),
            );
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
        renderTags: (value, getTagProps) =>
            value.map((option: string, index: number) => {
                const uuid = option;
                const { key, ...tagProps } = getTagProps({ index });
                return (
                    <Chip
                        key={key}
                        {...tagProps}
                        label={
                            uuidToUsername[uuid] ?? (
                                <Skeleton variant="text" width={60} />
                            )
                        }
                        variant="outlined"
                        color="primary"
                        avatar={
                            <img
                                style={{
                                    backgroundColor: "rgba(0, 0, 0, 0)",
                                }}
                                // TODO: Attribution - https://crafatar.com/#meta-attribution
                                src={`https://crafatar.com/renders/head/${uuid}?overlay`}
                                alt={`Player head of ${uuidToUsername[uuid] ?? "unknown"}`}
                            />
                        }
                    />
                );
            }),
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
                                        <Search fontSize="small" />
                                    </InputAdornment>
                                ),
                                endAdornment: loading && (
                                    <InputAdornment position="end">
                                        <CircularProgress size={20} />
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

interface UserMultiSelectProps {
    uuids: readonly string[];
    onSubmit: (uuids: string[]) => void;
    placeholder?: string;
    size?: "small" | "medium";
}

export const UserMultiSelect: React.FC<UserMultiSelectProps> = ({
    uuids,
    onSubmit,
    placeholder = "Add players",
    size = "small",
}) => {
    const queryClient = useQueryClient();
    const {
        uuids: options,
        filterOptions,
        renderOption,
        getOptionLabel,
        isOptionEqualToValue,
        renderTags,
    } = useUserSearchOptions<true>(uuids);
    const [loading, setLoading] = React.useState(false);

    return (
        <Autocomplete
            multiple
            freeSolo
            options={options}
            fullWidth
            size={size}
            autoHighlight
            filterOptions={filterOptions}
            renderOption={renderOption}
            getOptionLabel={getOptionLabel}
            isOptionEqualToValue={isOptionEqualToValue}
            renderTags={renderTags}
            value={[...uuids]}
            onChange={(_, newValues) => {
                setLoading(true);
                Promise.allSettled(
                    newValues.map((value) => {
                        // Allow UUIDs to be entered directly
                        if (isUUID(value)) {
                            return value;
                        }

                        return queryClient
                            .fetchQuery(getUUIDQueryOptions(value))
                            .then(({ uuid }) => {
                                return uuid;
                            })
                            .catch((error: unknown) => {
                                console.error(
                                    "Failed to fetch username",
                                    error,
                                );
                                throw error;
                            });
                    }),
                )
                    .then((results) => {
                        onSubmit(
                            results
                                .filter(
                                    (result) => result.status === "fulfilled",
                                )
                                .map((result) => result.value),
                        );
                    })
                    .catch((error: unknown) => {
                        console.error(
                            "Failed to settle all uuid promises",
                            error,
                        );
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
                                endAdornment: loading && (
                                    <InputAdornment position="end">
                                        <CircularProgress size={20} />
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
