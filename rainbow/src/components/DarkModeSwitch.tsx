import { DarkMode, LightMode } from "@mui/icons-material";
import { ToggleButton, ToggleButtonGroup, useColorScheme } from "@mui/material";

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
            <ToggleButton value="light">
                <LightMode />
            </ToggleButton>
            <ToggleButton value="system">Auto</ToggleButton>
            <ToggleButton value="dark">
                <DarkMode />
            </ToggleButton>
        </ToggleButtonGroup>
    );
};
