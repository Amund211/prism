import { TrendingDown, TrendingFlat, TrendingUp } from "@mui/icons-material";
import type { SvgIconComponent } from "@mui/icons-material";
import type { SvgIconOwnProps, SxProps, Theme } from "@mui/material";

import type { TrendDirection } from "#stats/format.ts";

// Direction → arrow icon, so an up/down/flat movement renders with the same
// icon everywhere.
const TREND_ICON: Record<TrendDirection, SvgIconComponent> = {
    up: TrendingUp,
    down: TrendingDown,
    flat: TrendingFlat,
};

interface TrendIconProps {
    readonly direction: TrendDirection;
    // Forwarded to the MUI icon. Omit `color` to inherit the surrounding text
    // colour. Use `sx` for a pixel size or palette-path colour the props can't
    // express, e.g. `{ fontSize: 16, color: "success.main" }`.
    readonly color?: SvgIconOwnProps["color"];
    readonly fontSize?: SvgIconOwnProps["fontSize"];
    readonly sx?: SxProps<Theme>;
}

export const TrendIcon: React.FC<TrendIconProps> = ({
    direction,
    color,
    fontSize,
    sx,
}) => {
    const Icon = TREND_ICON[direction];
    return <Icon color={color} fontSize={fontSize} sx={sx} />;
};
