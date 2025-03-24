import { DarkMode, LightMode, SettingsBrightness } from "@mui/icons-material";
import {
    ToggleButton,
    ToggleButtonGroup,
    Tooltip,
    useColorScheme,
} from "@mui/material";

export const DarkModeSwitch: React.FC = () => {
    const { mode, setMode } = useColorScheme();

    return (
        <ToggleButtonGroup
            size="small"
            value={mode ?? "system"}
            exclusive
            onChange={(_, newMode: "light" | "system" | "dark" | null) => {
                if (newMode === null) return;
                setMode(newMode);
            }}
        >
            <Tooltip title="Light mode">
                <ToggleButton value="light">
                    <LightMode />
                </ToggleButton>
            </Tooltip>
            <Tooltip title="System default">
                <ToggleButton value="system">
                    <SettingsBrightness />
                </ToggleButton>
            </Tooltip>
            <Tooltip title="Dark mode">
                <ToggleButton value="dark">
                    <DarkMode />
                </ToggleButton>
            </Tooltip>
        </ToggleButtonGroup>
    );
};
