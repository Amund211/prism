import { Search } from "@mui/icons-material";
import { InputAdornment, OutlinedInput } from "@mui/material";

interface UserSearchProps {
    onSubmit: (uuid: string) => void;
}

export const UserSearch: React.FC<UserSearchProps> = ({ onSubmit }) => {
    return (
        <OutlinedInput
            placeholder="Search user..."
            startAdornment={
                <InputAdornment position="start">
                    <Search fontSize="small" />
                </InputAdornment>
            }
            fullWidth
            size="small"
            onKeyDown={(event) => {
                if (event.key === "Enter") {
                    // TODO: Convert from username to UUID
                    const uuid = event.currentTarget.value;
                    onSubmit(uuid);
                }
            }}
        />
    );
};
