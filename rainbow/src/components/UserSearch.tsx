import { getUUIDQueryOptions } from "#queries/uuid.ts";
import { normalizeUUID } from "#helpers/uuid.ts";
import { useUUIDToUsername } from "#queries/username.ts";
import { Search } from "@mui/icons-material";
import {
    Autocomplete,
    type AutocompleteProps,
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
import { usePlayerVisits } from "#contexts/PlayerVisits/hooks.ts";
import { useKnownAliases } from "#contexts/KnownAliases/hooks.ts";
import { useCurrentUser } from "#contexts/CurrentUser/hooks.ts";

interface UserSearchProps {
    onSubmit: (uuid: string) => void;
    placeholder?: string;
    size?: "small" | "medium";
}

type SearchOption =
    | {
          type: "uuid";
          uuid: string;
      }
    | {
          type: "free-text";
          text: string;
      };

interface UserSearchOptions<Multiple extends boolean> {
    uuids: string[];
    filterOptions: AutocompleteProps<
        SearchOption,
        Multiple,
        true,
        false
    >["filterOptions"];
    renderOption: AutocompleteProps<
        SearchOption,
        Multiple,
        true,
        false
    >["renderOption"];
    getOptionLabel: AutocompleteProps<
        SearchOption,
        false,
        true,
        false
    >["getOptionLabel"];
    isOptionEqualToValue: AutocompleteProps<
        SearchOption,
        Multiple,
        true,
        false
    >["isOptionEqualToValue"];
    renderValue: AutocompleteProps<
        SearchOption,
        Multiple,
        true,
        false
    >["renderValue"];
}

const useUserSearchOptions = <Multiple extends boolean = false>(
    additionalUUIDs?: readonly string[],
): UserSearchOptions<Multiple> => {
    const { knownAliases } = useKnownAliases();
    const uuids = Object.keys(knownAliases);
    const uuidToUsername = useUUIDToUsername([
        ...new Set(uuids.concat(additionalUUIDs ?? [])),
    ]);
    const { orderUUIDsByScore } = usePlayerVisits();
    const { currentUser } = useCurrentUser();

    return {
        uuids,
        filterOptions: (options, { inputValue }) => {
            const namesForOptions = options.map((option) => {
                switch (option.type) {
                    case "free-text":
                        // The names can be anything here as long as it won't get filtered out
                        return { names: [option.text], option: option };
                    case "uuid": {
                        const name = uuidToUsername[option.uuid];
                        const names = knownAliases[option.uuid] ?? [];
                        if (!name) {
                            return {
                                names,
                                option,
                            };
                        }
                        return { names: [name, ...names], option };
                    }
                }
            });

            const uuidToOption = Object.fromEntries(
                options
                    .filter((option) => option.type === "uuid")
                    .map((option) => [option.uuid, option]),
            );

            const orderedUUIDs = orderUUIDsByScore(
                namesForOptions
                    .filter(({ names }) => {
                        return names.some((name) =>
                            name
                                .toLowerCase()
                                .includes(inputValue.toLowerCase()),
                        );
                    })
                    .map(({ option }) => {
                        if (option.type === "uuid") return option.uuid;
                        return null;
                    })
                    .filter((uuid) => uuid !== null),
                currentUser ?? undefined,
            );

            const orderedOptions: SearchOption[] = orderedUUIDs.map(
                (uuid) => uuidToOption[uuid],
            );

            return orderedOptions.concat(
                inputValue.trim()
                    ? [{ type: "free-text", text: inputValue.trim() }]
                    : [],
            );
        },
        renderOption: (props, option) => {
            // Render as "Search for {text}"
            const { key, ...optionProps } = props; // eslint-disable-line @typescript-eslint/no-unsafe-assignment
            switch (option.type) {
                case "free-text": {
                    // If text is UUID -> render as regular user option
                    const valueAsNormalizedUUID = normalizeUUID(option.text);
                    if (valueAsNormalizedUUID) {
                        return (
                            <UserOption
                                key={key} // eslint-disable-line @typescript-eslint/no-unsafe-assignment
                                uuid={valueAsNormalizedUUID}
                                optionProps={optionProps}
                            />
                        );
                    }

                    return (
                        <Stack
                            component="li"
                            key={key} // eslint-disable-line @typescript-eslint/no-unsafe-assignment
                            direction="row"
                            gap={2}
                            alignItems="center"
                            {...optionProps}
                        >
                            {/* HACK: Use an avatar to get the same layout as the UserOption*/}
                            <Avatar>
                                <Search fontSize="large" />
                            </Avatar>
                            <Typography variant="body1">
                                Search for &ldquo;{option.text}&rdquo;
                            </Typography>
                        </Stack>
                    );
                }
                case "uuid":
                    return (
                        <UserOption
                            key={key} // eslint-disable-line @typescript-eslint/no-unsafe-assignment
                            uuid={option.uuid}
                            optionProps={optionProps}
                        />
                    );
                default:
                    option satisfies never;
            }
            option satisfies never;
        },
        getOptionLabel: (option) => {
            switch (option.type) {
                case "uuid":
                    return uuidToUsername[option.uuid] ?? option.uuid;
                case "free-text":
                    return uuidToUsername[option.text] ?? option.text;
                default:
                    option satisfies never;
                    return "";
            }
        },
        isOptionEqualToValue: (option, value) => {
            if (option.type === "free-text") {
                // We never want the free-text search option at the bottom of the list to be highlighted
                return false;
            }

            switch (value.type) {
                case "uuid":
                    return option.uuid === value.uuid;
                case "free-text": {
                    // If the value of the submitted free-text was a uuid -> compare it with the option's uuid
                    const valueAsNormalizedUUID = normalizeUUID(value.text);
                    if (valueAsNormalizedUUID) {
                        return option.uuid === valueAsNormalizedUUID;
                    }

                    // The free-text value was submitted as a username. Compare it with the option's username
                    return (
                        uuidToUsername[option.uuid]?.toLowerCase() ===
                        value.text.toLowerCase()
                    );
                }
                default:
                    value satisfies never;
                    return false;
            }
        },
        renderValue: (value, getItemProps) => {
            if (!Array.isArray(value)) {
                // Don't render tags on single select
                return null;
            }

            return value.map((option: SearchOption, index: number) => {
                if (option.type === "free-text") {
                    return null;
                }

                return (
                    <Chip
                        {...getItemProps({ index })}
                        key={option.uuid}
                        label={
                            uuidToUsername[option.uuid] ?? (
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
                                src={`https://crafatar.com/renders/head/${option.uuid}?overlay`}
                                alt={`Player head of ${uuidToUsername[option.uuid] ?? "unknown"}`}
                            />
                        }
                    />
                );
            });
        },
    };
};

const UserOption: React.FC<{
    uuid: string;
    optionProps: React.HTMLAttributes<HTMLLIElement>;
}> = ({ uuid, optionProps }) => {
    const username = useUUIDToUsername([uuid])[uuid];
    return (
        <Stack
            component="li"
            direction="row"
            gap={2}
            alignItems="center"
            {...optionProps}
        >
            <Avatar
                src={`https://crafatar.com/renders/head/${uuid}?overlay`}
                alt={`Player head of ${username ?? "unknown"}`}
            />
            <Typography variant="body1">{username}</Typography>
        </Stack>
    );
};

export const UserSearch: React.FC<UserSearchProps> = ({
    onSubmit,
    placeholder = "Search players",
    size = "small",
}) => {
    const queryClient = useQueryClient();
    const { addKnownAlias } = useKnownAliases();
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
            options={uuids.map((uuid) => ({ type: "uuid" as const, uuid }))}
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
                if (value.type === "uuid") {
                    onSubmit(value.uuid);
                    return;
                }

                // Allow UUIDs to be entered directly
                const valueAsNormalizedUUID = normalizeUUID(value.text);
                if (valueAsNormalizedUUID) {
                    onSubmit(valueAsNormalizedUUID);
                    return;
                }

                setLoading(true);
                queryClient
                    .fetchQuery(getUUIDQueryOptions(value.text, addKnownAlias))
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
    const { addKnownAlias } = useKnownAliases();
    const {
        uuids: allUUIDs,
        filterOptions,
        renderOption,
        getOptionLabel,
        isOptionEqualToValue,
        renderValue,
    } = useUserSearchOptions<true>(uuids);
    const [loading, setLoading] = React.useState(false);

    return (
        <Autocomplete
            multiple
            options={allUUIDs.map((uuid) => ({ type: "uuid" as const, uuid }))}
            fullWidth
            size={size}
            autoHighlight
            filterOptions={filterOptions}
            renderOption={renderOption}
            getOptionLabel={getOptionLabel}
            isOptionEqualToValue={isOptionEqualToValue}
            renderValue={renderValue}
            value={[...uuids.map((uuid) => ({ type: "uuid" as const, uuid }))]}
            onChange={(_, newValues) => {
                setLoading(true);
                Promise.allSettled(
                    newValues.map(async (value) => {
                        if (value.type === "uuid") {
                            return value.uuid;
                        }

                        // Allow UUIDs to be entered directly
                        const valueAsNormalizedUUID = normalizeUUID(value.text);
                        if (valueAsNormalizedUUID) {
                            return valueAsNormalizedUUID;
                        }

                        return queryClient
                            .fetchQuery(
                                getUUIDQueryOptions(value.text, addKnownAlias),
                            )
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
