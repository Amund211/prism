import { UAParser } from "ua-parser-js";
import { createFileRoute } from "@tanstack/react-router";
import {
    Stack,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Typography,
} from "@mui/material";
import downloadWindowsURL from "#media/download_windows.png";
import downloadMacURL from "#media/download_mac.png";
import downloadLinuxURL from "#media/download_linux.png";

type OS = "Linux" | "Windows" | "Mac OS";

interface Download {
    os: OS;
    version: string;
    releasedAt: Date;
    link: string;
}

const DOWNLOADS: Download[] = [
    {
        os: "Windows",
        version: "1.9.0",
        releasedAt: new Date("2024-09-18T18:44:37Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.9.0/prism-v1.9.0-windows.exe",
    },
    {
        os: "Linux",
        version: "1.9.0",
        releasedAt: new Date("2024-09-18T18:44:37Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.9.0/prism-v1.9.0-linux",
    },
    {
        os: "Mac OS",
        version: "1.9.0",
        releasedAt: new Date("2024-09-18T18:44:37Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.9.0/prism-v1.9.0-mac.dmg",
    },
    {
        os: "Linux",
        version: "1.8.0",
        releasedAt: new Date("2024-09-06T22:31:59Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.8.0/prism-v1.8.0-linux",
    },
    {
        os: "Mac OS",
        version: "1.8.0",
        releasedAt: new Date("2024-09-06T22:31:59Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.8.0/prism-v1.8.0-mac.dmg",
    },
    {
        os: "Windows",
        version: "1.8.0",
        releasedAt: new Date("2024-09-06T22:31:59Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.8.0/prism-v1.8.0-windows.exe",
    },
    {
        os: "Linux",
        version: "1.7.0",
        releasedAt: new Date("2024-08-09T16:32:24Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.7.0/prism-v1.7.0-linux",
    },
    {
        os: "Mac OS",
        version: "1.7.0",
        releasedAt: new Date("2024-08-09T16:32:24Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.7.0/prism-v1.7.0-mac.dmg",
    },
    {
        os: "Windows",
        version: "1.7.0",
        releasedAt: new Date("2024-08-09T16:32:24Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.7.0/prism-v1.7.0-windows.exe",
    },
    {
        os: "Linux",
        version: "1.6.0",
        releasedAt: new Date("2024-03-31T20:52:46Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.6.0/prism-v1.6.0-linux",
    },
    {
        os: "Mac OS",
        version: "1.6.0",
        releasedAt: new Date("2024-03-31T20:52:46Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.6.0/prism-v1.6.0-mac.dmg",
    },
    {
        os: "Windows",
        version: "1.6.0",
        releasedAt: new Date("2024-03-31T20:52:46Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.6.0/prism-v1.6.0-windows.exe",
    },
];

export const Route = createFileRoute("/downloads")({
    component: RouteComponent,
});

const getOS = (): OS | "Unknown" => {
    const a = UAParser(navigator.userAgent);
    // Based on https://github.com/faisalman/ua-parser-js/blob/b9a710978e88ff1d5480886c2552efaccdad78ae/src/enums/ua-parser-enums.js
    switch (a.os.name?.toLowerCase()) {
        case "linux":
        case "arch":
        case "debian":
        case "fedora":
        case "gentoo":
        case "gnu":
        case "kubuntu":
        case "manjaro":
        case "raspbian":
        case "ubuntu":
        case "xubuntu":
            return "Linux";
        case "windows":
            return "Windows";
        case "macos":
            return "Mac OS";
        default:
            return "Unknown";
    }
};

const osLabel = (os: OS) => {
    switch (os) {
        case "Linux":
            return "Linux";
        case "Windows":
            return "Windows";
        case "Mac OS":
            return "Mac OS";
    }
};

function RouteComponent() {
    return (
        <Stack gap={5}>
            <meta
                name="description"
                content="Download Prism Overlay - a statistics overlay for Hypixel BedWars. Prism Overlay is a free and open-source overlay that provides real-time statistics when playing bedwars, and automatically tracks your stats."
            />
            <link rel="canonical" href="https://prismoverlay.com/downloads" />
            <Stack gap={1} alignItems="center">
                <LatestDownload />
                <Typography variant="body1">
                    Get started with real-time statistics and automated stat
                    tracking by downloading the Prism Overlay.
                </Typography>
            </Stack>
            <Stack gap={1} alignItems="center" paddingTop={10}>
                <Typography variant="h5">Archive</Typography>
                <Stack width="100%" gap={1}>
                    <TableContainer>
                        <Table aria-label="Archive" size="small" stickyHeader>
                            <TableHead>
                                <TableRow>
                                    <TableCell>
                                        <Typography variant="h6">
                                            Version
                                        </Typography>
                                    </TableCell>
                                    <TableCell>
                                        <Typography variant="h6">
                                            Operating System
                                        </Typography>
                                    </TableCell>
                                    <TableCell>
                                        <Typography variant="h6" align="right">
                                            Released At
                                        </Typography>
                                    </TableCell>
                                </TableRow>
                            </TableHead>
                            <TableBody>
                                {DOWNLOADS.map((download, i) => (
                                    <TableRow key={i}>
                                        <TableCell>
                                            <a href={download.link} download>
                                                <Typography variant="body1">
                                                    Prism overlay v
                                                    {download.version}
                                                </Typography>
                                            </a>
                                        </TableCell>
                                        <TableCell>
                                            <Typography variant="body1">
                                                {osLabel(download.os)}
                                            </Typography>
                                        </TableCell>
                                        <TableCell align="right">
                                            <Typography variant="body1">
                                                {download.releasedAt.toLocaleDateString(
                                                    undefined,
                                                    {
                                                        year: "numeric",
                                                        month: "long",
                                                        day: "numeric",
                                                    },
                                                )}
                                            </Typography>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </TableContainer>
                </Stack>
            </Stack>
            <Stack gap={1} alignItems="left">
                <Typography variant="caption" id="windows-logo">
                    [1] Windows and the Windows logo are registered trademarks
                    of the Microsoft Corporation.
                </Typography>
                <Typography variant="caption" id="mac-logo">
                    [2] macOS and the Apple logo are trademarks of Apple Inc.,
                    registered in the U.S. and other countries and regions.
                </Typography>
                <Typography variant="caption" id="linux-logo">
                    [3] Linux is the registered trademark of Linus Torvalds in
                    the U.S. and other countries. Tux is the copyright of Larry
                    Ewing lewing@isc.tamu.edu.
                </Typography>
            </Stack>
        </Stack>
    );
}

const LatestDownload = () => {
    switch (getOS()) {
        case "Windows":
            return <LatestDownloadWindows />;
        case "Mac OS":
            return <LatestDownloadMac />;
        case "Linux":
            return <LatestDownloadLinux />;
        default:
            return null;
    }
};

const LatestDownloadWindows = () => {
    const download = DOWNLOADS.find((d) => d.os === "Windows");
    if (!download) return null;

    return (
        <Stack alignItems="center">
            <a href={download.link} download>
                <img src={downloadWindowsURL} alt="Download for Windows" />
            </a>
            <a href="#windows-logo">
                <Typography variant="body1">[1]</Typography>
            </a>
        </Stack>
    );
};

const LatestDownloadMac = () => {
    const download = DOWNLOADS.find((d) => d.os === "Mac OS");
    if (!download) return null;

    return (
        <Stack alignItems="center">
            <a href={download.link} download>
                <img src={downloadMacURL} alt="Download for Mac" />
            </a>
            <a href="#mac-logo">
                <Typography variant="body1">[3]</Typography>
            </a>
        </Stack>
    );
};

const LatestDownloadLinux = () => {
    const download = DOWNLOADS.find((d) => d.os === "Linux");
    if (!download) return null;

    return (
        <Stack alignItems="center">
            <a href={download.link} download>
                <img src={downloadLinuxURL} alt="Download for Linux" />
            </a>
            <a href="#linux-logo">
                <Typography variant="body1">[3]</Typography>
            </a>
        </Stack>
    );
};
