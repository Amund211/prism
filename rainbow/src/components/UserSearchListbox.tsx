// This module pairs the useUserSearchListbox hook with the private components
// that implement the virtualized listbox. They are used together and only the
// hook is exported, so the fast-refresh "only export components" rule does not
// apply here.
/* oxlint-disable react/only-export-components */
import { autocompleteClasses, Popper, Stack } from "@mui/material";
import { styled } from "@mui/material/styles";
import React from "react";
import { List, useListRef } from "react-window";
import type { ListImperativeAPI, RowComponentProps } from "react-window";

// Height of a single option row, in px. Must fit the 40px player-head avatar (a
// cube head is ~46px tall) plus the option's vertical padding. Fixed because
// react-window needs a known row height; a username long enough to wrap onto a
// second line would clip, but Minecraft usernames are capped at 16 chars so a
// single line always fits.
const ROW_HEIGHT = 56;
// Vertical padding the MUI listbox renders around its options.
const LISTBOX_PADDING = 8;
// Number of rows shown before the listbox starts scrolling.
const MAX_VISIBLE_ROWS = 8;

// What renderOption hands to the virtualized listbox: the props MUI wants spread
// onto the option element, the content to render inside it, and a stable key
// used to scroll to an option during keyboard navigation.
export type RenderedRow = readonly [
    React.HTMLAttributes<HTMLLIElement>,
    React.ReactNode,
    string,
];

interface RowProps {
    readonly rows: readonly RenderedRow[];
}

// The listbox class is applied directly to react-window's <ul> (the List root,
// tagName="ul"), so reset the browser default ul padding/margin on that element
// itself. The rows' vertical inset is handled in JS via LISTBOX_PADDING, so the
// list only needs box-sizing and a clean slate here.
const StyledPopper = styled(Popper)({
    [`& .${autocompleteClasses.listbox}`]: {
        boxSizing: "border-box",
        padding: 0,
        margin: 0,
    },
});

// react-window owns this prop shape (style is a mutable CSSProperties), so the
// parameter cannot be made fully readonly.
// oxlint-disable-next-line typescript/prefer-readonly-parameter-types
function VirtualizedRow({ index, style, rows }: RowComponentProps<RowProps>) {
    const [optionProps, content] = rows[index];
    const top = typeof style.top === "number" ? style.top : 0;

    return (
        <Stack
            component="li"
            direction="row"
            // oxlint-disable-next-line react/jsx-props-no-spreading
            {...optionProps}
            style={{ ...style, top: top + LISTBOX_PADDING, margin: 0 }}
            sx={{ gap: 2, alignItems: "center" }}
        >
            {content}
        </Stack>
    );
}

interface VirtualizedListboxProps extends React.HTMLAttributes<HTMLElement> {
    readonly internalListRef: React.Ref<ListImperativeAPI>;
    // Filled in by the listbox with a map of option key -> row index, so keyboard
    // navigation can scroll a highlighted (possibly off-screen) row into view.
    readonly optionIndexMapRef: React.RefObject<ReadonlyMap<string, number>>;
}

// Adapter that renders the Autocomplete options through react-window so only the
// visible rows are mounted. Each mounted row resolves its own username lazily,
// so opening the dropdown no longer resolves the whole option list at once.
const VirtualizedListbox = React.forwardRef<HTMLDivElement, VirtualizedListboxProps>(
    function VirtualizedListbox(props, ref) {
        const { children, internalListRef, optionIndexMapRef, ...other } = props;
        const rows = children as unknown as readonly RenderedRow[];

        React.useEffect(() => {
            const optionIndexMap = new Map<string, number>();
            for (const [index, row] of rows.entries()) {
                optionIndexMap.set(row[2], index);
            }
            optionIndexMapRef.current = optionIndexMap;
        }, [rows, optionIndexMapRef]);

        const itemCount = rows.length;
        const height = Math.min(itemCount, MAX_VISIBLE_ROWS) * ROW_HEIGHT;
        // MUI's listbox className must live on the scroll container (the ul that
        // List renders); the remaining props (role, aria, handlers) stay on the
        // wrapper. The listbox style is dropped because List sizes itself.
        const { className, style, ...otherProps } = other;
        void style;

        return (
            // oxlint-disable-next-line react/jsx-props-no-spreading
            <div ref={ref} {...otherProps}>
                <List
                    className={className}
                    listRef={internalListRef}
                    rowCount={itemCount}
                    rowHeight={ROW_HEIGHT}
                    rowComponent={VirtualizedRow}
                    rowProps={{ rows }}
                    style={{ height: height + 2 * LISTBOX_PADDING, width: "100%" }}
                    overscanCount={5}
                    tagName="ul"
                />
            </div>
        );
    },
);

// Wires up the virtualized listbox for an Autocomplete: returns the slot config
// to spread onto the component plus scrollToKey, which keeps keyboard navigation
// working by scrolling the (possibly off-screen) highlighted row into view.
export const useUserSearchListbox = () => {
    const listRef = useListRef(null);
    const optionIndexMapRef = React.useRef<ReadonlyMap<string, number>>(new Map());

    const scrollToKey = React.useCallback(
        (key: string | null) => {
            if (key === null) {
                return;
            }
            const index = optionIndexMapRef.current.get(key);
            if (index !== undefined) {
                listRef.current?.scrollToRow({ index, align: "auto" });
            }
        },
        [listRef],
    );

    const slots = React.useMemo(() => ({ popper: StyledPopper }), []);
    const slotProps = React.useMemo(
        () => ({
            listbox: {
                component: VirtualizedListbox,
                internalListRef: listRef,
                optionIndexMapRef,
            },
        }),
        [listRef],
    );

    return { disableListWrap: true, slots, slotProps, scrollToKey };
};
