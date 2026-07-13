import { Search } from "@mui/icons-material";
import {
    Autocomplete,
    Avatar,
    Chip,
    CircularProgress,
    InputAdornment,
    Skeleton,
    TextField,
    Typography,
} from "@mui/material";
import type { AutocompleteProps } from "@mui/material";
import { useQueryClient } from "@tanstack/react-query";
import React from "react";

import { useCurrentUser } from "#contexts/CurrentUser/hooks.ts";
import { currentKnownUsernames } from "#contexts/KnownAliases/helpers.ts";
import { useKnownAliases } from "#contexts/KnownAliases/hooks.ts";
import { usePlayerVisits } from "#contexts/PlayerVisits/hooks.ts";
import { normalizeUUID } from "#helpers/uuid.ts";
import { useUUIDToUsername } from "#queries/username.ts";
import { getUUIDQueryOptions } from "#queries/uuid.ts";

import { PlayerHead } from "./player.tsx";
import { useUserSearchListbox } from "./UserSearchListbox.tsx";
import type { RenderedRow } from "./UserSearchListbox.tsx";

interface UserSearchProps {
    onSubmit: (uuid: string) => void;
    placeholder?: string;
    size?: "small" | "medium";
}

type SearchOption =
    | {
          readonly type: "uuid";
          readonly uuid: string;
      }
    | {
          readonly type: "free-text";
          readonly text: string;
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
    renderValue: AutocompleteProps<SearchOption, Multiple, true, false>["renderValue"];
}

const useUserSearchOptions = <Multiple extends boolean = false>(
    additionalUUIDs?: readonly string[],
): UserSearchOptions<Multiple> => {
    const { knownAliases } = useKnownAliases();
    const uuids = Object.keys(knownAliases);
    // Serve names for the (potentially huge) known-alias history straight from
    // local storage so opening the page doesn't resolve every uuid over the
    // network. Only the small set of explicitly selected uuids (e.g. the chips
    // in UserMultiSelect) is resolved to stay fresh.
    const localUsernames = currentKnownUsernames(knownAliases);
    const resolvedUsernames = useUUIDToUsername(additionalUUIDs ?? []);
    const uuidToUsername = { ...localUsernames, ...resolvedUsernames };
    const { orderUUIDsByScore } = usePlayerVisits();
    const { currentUser } = useCurrentUser();

    return {
        uuids,
        filterOptions: (options, { inputValue }) => {
            const namesForOptions = options.map((option) => {
                switch (option.type) {
                    case "free-text": {
                        // The names can be anything here as long as it won't get filtered out
                        return { names: [option.text], option };
                    }
                    case "uuid": {
                        const name = uuidToUsername[option.uuid];
                        const names = knownAliases[option.uuid] ?? [];
                        if (name === undefined) {
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
                            name.toLowerCase().includes(inputValue.toLowerCase()),
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

            return [
                ...orderedOptions,
                ...(inputValue.trim()
                    ? [{ type: "free-text" as const, text: inputValue.trim() }]
                    : []),
            ];
        },
        renderOption: (props, option) => {
            // The listbox is virtualized (see UserSearchListbox), so renderOption
            // returns data the row component renders instead of an element: the
            // props MUI wants on the option, the content, and a stable key.
            const { key, ...optionProps } = props;
            void key;
            // The tuple is consumed by the virtualized listbox, but MUI types
            // renderOption as returning a ReactNode. Cast to a non-Promise
            // ReactNode so the tuple is accepted without widening the return
            // type to include Promise (which ReactNode otherwise allows).
            return [
                optionProps,
                // oxlint-disable-next-line eslint/no-use-before-define
                renderSearchOptionContent(option),
                // oxlint-disable-next-line eslint/no-use-before-define
                searchOptionKey(option),
            ] satisfies RenderedRow as Exclude<React.ReactNode, Promise<unknown>>;
        },
        getOptionLabel: (option) => {
            switch (option.type) {
                case "uuid": {
                    return uuidToUsername[option.uuid] ?? option.uuid;
                }
                case "free-text": {
                    return uuidToUsername[option.text] ?? option.text;
                }
                default: {
                    option satisfies never;
                    return "";
                }
            }
        },
        isOptionEqualToValue: (option, value) => {
            if (option.type === "free-text") {
                // We never want the free-text search option at the bottom of the list to be highlighted
                return false;
            }

            switch (value.type) {
                case "uuid": {
                    return option.uuid === value.uuid;
                }
                case "free-text": {
                    // If the value of the submitted free-text was a uuid -> compare it with the option's uuid
                    const valueAsNormalizedUUID = normalizeUUID(value.text);
                    if (valueAsNormalizedUUID !== null) {
                        return option.uuid === valueAsNormalizedUUID;
                    }

                    // The free-text value was submitted as a username. Compare it with the option's username
                    return (
                        uuidToUsername[option.uuid]?.toLowerCase() ===
                        value.text.toLowerCase()
                    );
                }
                default: {
                    value satisfies never;
                    return false;
                }
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

                const username = uuidToUsername[option.uuid];

                return (
                    <Chip
                        // oxlint-disable-next-line react/jsx-props-no-spreading
                        {...getItemProps({ index })}
                        key={option.uuid}
                        label={username ?? <Skeleton variant="text" width={60} />}
                        variant="outlined"
                        color="primary"
                        avatar={
                            // NOTE: Duplicated from PlayerHead component due to issues with sizing
                            <img
                                style={{
                                    backgroundColor: "rgba(0, 0, 0, 0)",
                                }}
                                src={`https://api.mineatar.io/head/${option.uuid}?overlay=true`}
                                alt={`${username ?? "unknown"}'s player head`}
                            />
                        }
                    />
                );
            });
        },
    };
};

// A stable key per option, used by the virtualized listbox to scroll the
// highlighted row into view during keyboard navigation.
const searchOptionKey = (option: SearchOption): string =>
    option.type === "uuid" ? `uuid:${option.uuid}` : `free-text:${option.text}`;

// The content rendered inside a virtualized option row (the row's <li> wrapper
// and positioning are provided by the listbox). Resolving the username here
// means only the rows actually mounted by the virtualizer hit the network.
const UserOptionContent: React.FC<{ uuid: string }> = ({ uuid }) => {
    const username = useUUIDToUsername([uuid])[uuid];
    return (
        <>
            <PlayerHead uuid={uuid} username={username} variant="cube" />
            <Typography variant="body1">{username}</Typography>
        </>
    );
};

const renderSearchOptionContent = (option: SearchOption): React.ReactNode => {
    switch (option.type) {
        case "free-text": {
            // If the text is a UUID -> render as a regular user option.
            const valueAsNormalizedUUID = normalizeUUID(option.text);
            if (valueAsNormalizedUUID !== null) {
                return <UserOptionContent uuid={valueAsNormalizedUUID} />;
            }

            return (
                <>
                    {/* HACK: Use an avatar to get the same layout as UserOptionContent */}
                    <Avatar>
                        <Search fontSize="large" />
                    </Avatar>
                    <Typography variant="body1">
                        Search for &ldquo;{option.text}&rdquo;
                    </Typography>
                </>
            );
        }
        case "uuid": {
            return <UserOptionContent uuid={option.uuid} />;
        }
    }
};

export const UserSearch: React.FC<UserSearchProps> = ({
    onSubmit,
    placeholder = "Search players",
    size = "small",
}) => {
    const queryClient = useQueryClient();
    const { uuids, filterOptions, renderOption, getOptionLabel, isOptionEqualToValue } =
        useUserSearchOptions();
    const { disableListWrap, slots, slotProps, scrollToKey } = useUserSearchListbox();
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
            // Home/End are disabled: MUI resolves them by locating the target
            // option's DOM node, but the listbox is virtualized so the first/last
            // option usually isn't mounted. That made them jump only to the edge of
            // the currently mounted window instead of the true first/last option.
            // Arrow keys (which scroll the virtualizer via scrollToKey) still work.
            handleHomeEndKeys={false}
            disableListWrap={disableListWrap}
            slots={slots}
            slotProps={slotProps}
            filterOptions={filterOptions}
            renderOption={renderOption}
            getOptionLabel={getOptionLabel}
            isOptionEqualToValue={isOptionEqualToValue}
            onHighlightChange={(_, option) => {
                scrollToKey(option === null ? null : searchOptionKey(option));
            }}
            onChange={(_, value) => {
                if (value === null) return;

                if (value.type === "uuid") {
                    onSubmit(value.uuid);
                    return;
                }

                // Allow UUIDs to be entered directly
                const valueAsNormalizedUUID = normalizeUUID(value.text);
                if (valueAsNormalizedUUID !== null) {
                    onSubmit(valueAsNormalizedUUID);
                    return;
                }

                setLoading(true);
                void (async () => {
                    try {
                        const { uuid } = await queryClient.fetchQuery(
                            getUUIDQueryOptions(value.text),
                        );
                        onSubmit(uuid);
                    } catch (error: unknown) {
                        // oxlint-disable-next-line eslint/no-console
                        console.error("Failed to fetch username", error);
                    } finally {
                        setLoading(false);
                    }
                })();
            }}
            renderInput={(params) => {
                return (
                    <TextField
                        // oxlint-disable-next-line react/jsx-props-no-spreading
                        {...params}
                        placeholder={placeholder}
                        slotProps={{
                            ...params.slotProps,
                            input: {
                                ...params.slotProps.input,
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
    readonly uuids: readonly string[];
    readonly onSubmit: (uuids: readonly string[]) => void;
    readonly placeholder?: string;
    readonly size?: "small" | "medium";
}

export const UserMultiSelect: React.FC<UserMultiSelectProps> = ({
    uuids,
    onSubmit,
    placeholder = "Add players",
    size = "small",
}) => {
    const queryClient = useQueryClient();
    const {
        uuids: allUUIDs,
        filterOptions,
        renderOption,
        getOptionLabel,
        isOptionEqualToValue,
        renderValue,
    } = useUserSearchOptions<true>(uuids);
    const { disableListWrap, slots, slotProps, scrollToKey } = useUserSearchListbox();
    const [loading, setLoading] = React.useState(false);

    return (
        <Autocomplete
            multiple
            options={allUUIDs.map((uuid) => ({ type: "uuid" as const, uuid }))}
            fullWidth
            size={size}
            autoHighlight
            // Disabled because the virtualized listbox usually hasn't mounted the
            // first/last option that MUI's Home/End handling looks up by DOM node;
            // see the note on UserSearch above.
            handleHomeEndKeys={false}
            disableListWrap={disableListWrap}
            slots={slots}
            slotProps={slotProps}
            filterOptions={filterOptions}
            renderOption={renderOption}
            getOptionLabel={getOptionLabel}
            isOptionEqualToValue={isOptionEqualToValue}
            renderValue={renderValue}
            value={uuids.map((uuid) => ({ type: "uuid" as const, uuid }))}
            onHighlightChange={(_, option) => {
                scrollToKey(option === null ? null : searchOptionKey(option));
            }}
            onChange={(_, newValues) => {
                setLoading(true);
                void (async () => {
                    try {
                        const results = await Promise.allSettled(
                            newValues.map(async (value) => {
                                if (value.type === "uuid") {
                                    return value.uuid;
                                }

                                // Allow UUIDs to be entered directly
                                const valueAsNormalizedUUID = normalizeUUID(value.text);
                                if (valueAsNormalizedUUID !== null) {
                                    return valueAsNormalizedUUID;
                                }

                                try {
                                    const { uuid } = await queryClient.fetchQuery(
                                        getUUIDQueryOptions(value.text),
                                    );
                                    return uuid;
                                } catch (error: unknown) {
                                    // oxlint-disable-next-line eslint/no-console
                                    console.error("Failed to fetch username", error);
                                    throw error;
                                }
                            }),
                        );
                        onSubmit(
                            results
                                .filter((result) => result.status === "fulfilled")
                                .map((result) => result.value),
                        );
                    } catch (error: unknown) {
                        // oxlint-disable-next-line eslint/no-console
                        console.error("Failed to settle all uuid promises", error);
                    } finally {
                        setLoading(false);
                    }
                })();
            }}
            renderInput={(params) => {
                return (
                    <TextField
                        // oxlint-disable-next-line react/jsx-props-no-spreading
                        {...params}
                        placeholder={placeholder}
                        slotProps={{
                            ...params.slotProps,
                            input: {
                                ...params.slotProps.input,
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
