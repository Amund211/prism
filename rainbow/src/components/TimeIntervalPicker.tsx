import {
    endOfLastDay,
    endOfLastMonth,
    endOfLastWeek,
    type TimeIntervalDefinition,
} from "#intervals.ts";
import { CalendarMonth } from "@mui/icons-material";
import { Button, Menu, MenuItem, Tooltip, Typography } from "@mui/material";
import React from "react";

interface TimeIntervalPickerProps {
    intervalDefinition: TimeIntervalDefinition;
    onIntervalChange: (intervalDefinition: TimeIntervalDefinition) => void;
}

export const TimeIntervalPicker: React.FC<TimeIntervalPickerProps> = ({
    intervalDefinition,
    onIntervalChange,
}) => {
    const [anchorEl, setAnchorEl] = React.useState<null | HTMLElement>(null);
    const open = Boolean(anchorEl);
    const handleClick = (event: React.MouseEvent<HTMLButtonElement>) => {
        setAnchorEl(event.currentTarget);
    };
    const handleClose = () => {
        setAnchorEl(null);
    };

    const formattedDate = intervalDefinition.date?.toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
    });

    let shortIntervalDescription = "Unknown interval";
    let longIntervalDescription = "Unknown interval";
    switch (intervalDefinition.type) {
        case "contained":
            if (formattedDate !== undefined) {
                shortIntervalDescription = `Current interval at ${formattedDate}`;
                longIntervalDescription = `Show the stats for the current day, week, or month, as they would have appeared at ${formattedDate}.`;
                break;
            }
            shortIntervalDescription = "Current interval";
            longIntervalDescription =
                "Show the stats for the current day, week, or month.";
            break;
        case "until":
            if (formattedDate !== undefined) {
                shortIntervalDescription = `Last X days at ${formattedDate}`;
                longIntervalDescription = `Show the stats for the last 1, 7, or 30 days, as they would have appeared at ${formattedDate}.`;
                break;
            }
            shortIntervalDescription = "Last X days";
            longIntervalDescription =
                "Show the stats for the last 1, 7, or 30 days";
            break;
        default:
            intervalDefinition.type satisfies never;
    }

    return (
        <>
            <Tooltip title={longIntervalDescription}>
                <Button
                    id="interval-picker-button"
                    size="small"
                    variant="outlined"
                    startIcon={<CalendarMonth />}
                    aria-controls={open ? "interval-picker-menu" : undefined}
                    aria-haspopup="true"
                    aria-expanded={open ? "true" : undefined}
                    onClick={handleClick}
                >
                    <Typography variant="caption">
                        {shortIntervalDescription}
                    </Typography>
                </Button>
            </Tooltip>
            <Menu
                id="interval-picker-menu"
                anchorEl={anchorEl}
                anchorOrigin={{
                    vertical: "bottom",
                    horizontal: "right",
                }}
                open={open}
                onClose={handleClose}
                slotProps={{
                    list: {
                        "aria-labelledby": "interval-picker-button",
                    },
                }}
            >
                <Tooltip
                    title="Show stats for the current day, week, or month."
                    placement="left"
                >
                    <MenuItem
                        onClick={() => {
                            onIntervalChange({ type: "contained" });
                            handleClose();
                        }}
                    >
                        Current interval
                    </MenuItem>
                </Tooltip>
                <Tooltip
                    // TODO: We currently do last <days in month> days, not last 30 days
                    title="Show stats for the last 1, 7, or 30 days."
                    placement="left"
                >
                    <MenuItem
                        onClick={() => {
                            onIntervalChange({ type: "until" });
                            handleClose();
                        }}
                    >
                        Last X days
                    </MenuItem>
                </Tooltip>
                <Tooltip
                    title="Show the stats for the current day, week, or month, as they would have appeared at the end of yesterday."
                    placement="left"
                >
                    <MenuItem
                        onClick={() => {
                            onIntervalChange({
                                type: "contained",
                                date: endOfLastDay(new Date()),
                            });
                            handleClose();
                        }}
                    >
                        Yesterday
                    </MenuItem>
                </Tooltip>
                <Tooltip
                    title="Show the stats for the current day, week, or month, as they would have appeared at the end of last week."
                    placement="left"
                >
                    <MenuItem
                        onClick={() => {
                            onIntervalChange({
                                type: "contained",
                                date: endOfLastWeek(new Date()),
                            });
                            handleClose();
                        }}
                    >
                        Last week
                    </MenuItem>
                </Tooltip>
                <Tooltip
                    title="Show the stats for the current day, week, or month, as they would have appeared at the end of last month."
                    placement="left"
                >
                    <MenuItem
                        onClick={() => {
                            onIntervalChange({
                                type: "contained",
                                date: endOfLastMonth(new Date()),
                            });
                            handleClose();
                        }}
                    >
                        Last month
                    </MenuItem>
                </Tooltip>
                {/*
                <Tooltip
                    // TODO: We currently do last <days in month> days, not last 30 days
                    title="Show stats for the last 1, 7, or 30 days, as they would have appeared at at a specified date."
                    placement="left"
                >
                    <MenuItem
                        onClick={() => {
                            onIntervalChange({ type: "until" });
                            handleClose();
                        }}
                    >
                        Custom
                    </MenuItem>
                </Tooltip>
                */}
            </Menu>
        </>
    );
};
