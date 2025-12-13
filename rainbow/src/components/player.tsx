import { Avatar } from "@mui/material";

interface PlayerHeadProps {
    uuid: string;
    username?: string;
    variant: "cube" | "face";
    width?: number;
}

export const PlayerHead: React.FC<PlayerHeadProps> = ({
    uuid,
    username,
    variant,
    width = 40,
}) => {
    // Cubes at max scale are 886x1024, faces are square
    const aspectRatio = variant === "cube" ? 886 / 1024 : 1;
    const scale = (width / 4).toFixed();

    const link =
        variant === "cube"
            ? `https://api.mineatar.io/head/${uuid}?overlay=true&scale=${scale}`
            : `https://api.mineatar.io/face/${uuid}?overlay=true&scale=${scale}`;

    return (
        <Avatar
            src={link}
            alt={`${username ?? "unknown"}'s player head`}
            variant="rounded"
            sx={{ width: width, height: width / aspectRatio }}
        />
    );
};
