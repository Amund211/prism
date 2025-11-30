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
    useColorScheme,
} from "@mui/material";
import downloadWindowsURL from "#media/download_windows.png";
import downloadMacURL from "#media/download_mac.png";
import downloadLinuxURL from "#media/download_linux.png";
import tuxURL from "#media/tux.svg";
import windowsLogoURL from "#media/windows_logo.svg";
import macLogoURL from "#media/mac_logo.svg";
import macLogoGreyURL from "#media/mac_logo_grey.svg";
import autoWhoURL from "#media/autowho.webp";

type OS = "Linux" | "Windows" | "Mac OS";

interface Download {
    os: OS;
    version: string;
    releasedAt: Date;
    link: string;
}

// Sourced from: https://github.com/Amund211/prism/releases
const DOWNLOADS: Download[] = [
    {
        os: "Windows",
        version: "1.11.0",
        releasedAt: new Date("2025-11-30T17:07:33Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.11.0/prism-v1.11.0-windows.exe",
    },
    {
        os: "Mac OS",
        version: "1.11.0",
        releasedAt: new Date("2025-11-30T17:07:33Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.11.0/prism-v1.11.0-mac.dmg",
    },
    {
        os: "Linux",
        version: "1.11.0",
        releasedAt: new Date("2025-11-30T17:07:33Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.11.0/prism-v1.11.0-linux",
    },
    {
        os: "Windows",
        version: "1.10.0",
        releasedAt: new Date("2025-10-03T23:21:09Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.10.0/prism-v1.10.0-windows.exe",
    },
    {
        os: "Mac OS",
        version: "1.10.0",
        releasedAt: new Date("2025-10-03T23:21:09Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.10.0/prism-v1.10.0-mac.dmg",
    },
    {
        os: "Linux",
        version: "1.10.0",
        releasedAt: new Date("2025-10-03T23:21:09Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.10.0/prism-v1.10.0-linux",
    },
    {
        os: "Windows",
        version: "1.9.0",
        releasedAt: new Date("2024-09-18T18:44:37Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.9.0/prism-v1.9.0-windows.exe",
    },
    {
        os: "Mac OS",
        version: "1.9.0",
        releasedAt: new Date("2024-09-18T18:44:37Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.9.0/prism-v1.9.0-mac.dmg",
    },
    {
        os: "Linux",
        version: "1.9.0",
        releasedAt: new Date("2024-09-18T18:44:37Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.9.0/prism-v1.9.0-linux",
    },
    {
        os: "Windows",
        version: "1.8.0",
        releasedAt: new Date("2024-09-06T22:31:59Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.8.0/prism-v1.8.0-windows.exe",
    },
    {
        os: "Mac OS",
        version: "1.8.0",
        releasedAt: new Date("2024-09-06T22:31:59Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.8.0/prism-v1.8.0-mac.dmg",
    },
    {
        os: "Linux",
        version: "1.8.0",
        releasedAt: new Date("2024-09-06T22:31:59Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.8.0/prism-v1.8.0-linux",
    },
    {
        os: "Windows",
        version: "1.7.0",
        releasedAt: new Date("2024-08-09T16:32:24Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.7.0/prism-v1.7.0-windows.exe",
    },
    {
        os: "Mac OS",
        version: "1.7.0",
        releasedAt: new Date("2024-08-09T16:32:24Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.7.0/prism-v1.7.0-mac.dmg",
    },
    {
        os: "Linux",
        version: "1.7.0",
        releasedAt: new Date("2024-08-09T16:32:24Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.7.0/prism-v1.7.0-linux",
    },
    {
        os: "Windows",
        version: "1.6.0",
        releasedAt: new Date("2024-03-31T20:52:46Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.6.0/prism-v1.6.0-windows.exe",
    },
    {
        os: "Mac OS",
        version: "1.6.0",
        releasedAt: new Date("2024-03-31T20:52:46Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.6.0/prism-v1.6.0-mac.dmg",
    },
    {
        os: "Linux",
        version: "1.6.0",
        releasedAt: new Date("2024-03-31T20:52:46Z"),
        link: "https://github.com/Amund211/prism/releases/download/v1.6.0/prism-v1.6.0-linux",
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

const getOSLogoImage = (os: OS, colorScheme: "light" | "dark") => {
    switch (os) {
        case "Linux":
            return {
                url: tuxURL,
                aspectRatio: 1,
            };
        case "Windows":
            return {
                url: windowsLogoURL,
                aspectRatio: 1,
            };
        case "Mac OS":
            if (colorScheme === "dark") {
                return {
                    url: macLogoGreyURL,
                    aspectRatio: 1,
                };
            }
            return {
                url: macLogoURL,
                aspectRatio: 814 / 1000,
            };
    }
};

const OSLogo = ({ os, height }: { os: OS; height: number }) => {
    const { mode, systemMode } = useColorScheme();
    const activeMode = mode === "system" ? systemMode : mode;
    const image = getOSLogoImage(os, activeMode ?? "light");

    return (
        <img
            src={image.url}
            alt={`${os} logo`}
            width={height * image.aspectRatio}
            height={height}
        />
    );
};

const OSLogoAttribution = ({ os }: { os: OS }) => {
    const getAttributionId = (os: OS) => {
        switch (os) {
            case "Windows":
                return "windows-logo";
            case "Mac OS":
                return "mac-logo";
            case "Linux":
                return "linux-logo";
        }
    };
    const getAttributionText = (os: OS) => {
        switch (os) {
            case "Windows":
                return "[1]";
            case "Mac OS":
                return "[2]";
            case "Linux":
                return "[3]";
        }
    };

    return (
        <a href={`#${getAttributionId(os)}`}>
            <Typography variant="body1">{getAttributionText(os)}</Typography>
        </a>
    );
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
                <Typography variant="body1">
                    Get started with real-time statistics and automated stat
                    tracking by downloading the Prism Overlay.
                </Typography>
                <LatestDownload />
            </Stack>
            <AutoWhoVideo />
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
                                            <Stack direction="row" gap={1}>
                                                <OSLogoAttribution
                                                    os={download.os}
                                                />
                                                <OSLogo
                                                    os={download.os}
                                                    height={20}
                                                />
                                                <Typography variant="body1">
                                                    {osLabel(download.os)}
                                                </Typography>
                                            </Stack>
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

const AutoWhoVideo = () => {
    return (
        <Stack gap={1} alignItems="center">
            <Stack maxWidth="calc(min(100vw, 800px))" width="100%">
                <img
                    alt="Video of a bedwars game starting, with the Prism Overlay in the top left corner. When the game starts, the overlay automatically types '/who' to show all players."
                    src={autoWhoURL}
                    width="100%"
                    aria-describedby="auto-who-video-description"
                />
            </Stack>
            <Typography variant="caption" id="auto-who-video-description">
                The Prism Overlay automatically typing /who to show all players
                and displaying their stats.
            </Typography>
        </Stack>
    );
};

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
            <OSLogoAttribution os="Windows" />
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
            <OSLogoAttribution os="Mac OS" />
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
            <OSLogoAttribution os="Linux" />
        </Stack>
    );
};
