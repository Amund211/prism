import { DarkMode, LightMode } from "@mui/icons-material";
import { IconButton, Tooltip, useColorScheme, useMediaQuery } from "@mui/material";

/**
 * A single button that switches between light and dark.
 *
 * Three modes are stored, but only two are offered: the scheme you see and its
 * opposite. A press stores the opposite explicitly, unless that scheme is the
 * one the OS asks for — then it stores "system" so the user keeps following the
 * OS. Consulting the OS only on press means a scheduled OS switch cannot
 * discard a pinned override.
 *
 * https://lea.verou.me/blog/2026/dark-mode-toggles
 */
export const DarkModeSwitch: React.FC = () => {
    const { mode, systemMode, setMode } = useColorScheme();
    const systemPrefersDark = useMediaQuery("(prefers-color-scheme: dark)", {
        noSsr: true,
    });

    const systemScheme = systemPrefersDark ? "dark" : "light";
    const activeScheme = (mode === "system" ? systemMode : mode) ?? systemScheme;
    const target = activeScheme === "dark" ? "light" : "dark";
    const targetIsSystem = target === systemScheme;

    const label = `Switch to ${target} mode${targetIsSystem ? " (system default)" : ""}`;

    return (
        <Tooltip title={label}>
            <IconButton
                aria-label={label}
                onClick={() => {
                    setMode(targetIsSystem ? "system" : target);
                }}
            >
                {target === "dark" ? <DarkMode /> : <LightMode />}
            </IconButton>
        </Tooltip>
    );
};
