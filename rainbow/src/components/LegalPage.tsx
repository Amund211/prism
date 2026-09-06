import { Stack, Typography } from "@mui/material";
import React from "react";

/**
 * Shell for the /terms and /privacy pages: heading, "last updated" line, and
 * the head tags both pages need. `path` is the route path, e.g. "/privacy".
 */
export const LegalPage: React.FC<{
    title: string;
    lastUpdated: string;
    description: string;
    path: string;
    children: React.ReactNode;
}> = ({ title, lastUpdated, description, path, children }) => {
    return (
        <Stack
            sx={{
                gap: 3,
                maxWidth: "72ch",
            }}
        >
            <meta name="description" content={description} />
            <link rel="canonical" href={`https://prismoverlay.com${path}`} />
            <Stack sx={{ gap: 0.5 }}>
                <Typography variant="h4" component="h1">
                    {title}
                </Typography>
                <Typography variant="body2" color="textSecondary">
                    Last updated {lastUpdated}
                </Typography>
            </Stack>
            {children}
        </Stack>
    );
};

export const LegalSection: React.FC<{
    title: string;
    children: React.ReactNode;
}> = ({ title, children }) => {
    return (
        <Stack component="section" sx={{ gap: 1 }}>
            <Typography variant="h6" component="h2">
                {title}
            </Typography>
            {children}
        </Stack>
    );
};

export const LegalList: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    return (
        <Stack
            component="ul"
            sx={{
                gap: 1,
                marginY: 0,
                paddingLeft: 3,
            }}
        >
            {children}
        </Stack>
    );
};

export const LegalListItem: React.FC<{ children: React.ReactNode }> = ({
    children,
}) => {
    return (
        <Typography component="li" variant="body1">
            {children}
        </Typography>
    );
};
