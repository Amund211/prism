import { Typography } from "@mui/material";
import { createFileRoute, Link } from "@tanstack/react-router";

import {
    LegalList,
    LegalListItem,
    LegalPage,
    LegalSection,
} from "#components/LegalPage.tsx";

const LAST_UPDATED = "7 September 2026";

const DISCORD_URL = "https://discord.gg/k4FGUnEHYg";

const DiscordLink = () => (
    <a href={DISCORD_URL} target="_blank" rel="noreferrer">
        Discord
    </a>
);

function RouteComponent() {
    return (
        <LegalPage
            title="Privacy policy"
            lastUpdated={LAST_UPDATED}
            path="/privacy"
            description="How Prism Overlay handles data: what the overlay, the website and the backend store, which third parties are involved, and how to get your statistics removed."
        >
            <LegalSection title="Scope">
                <Typography variant="body1">
                    This policy describes how Prism Overlay handles data in the overlay
                    application, the website at prismoverlay.com, and the backend API
                    that serves them.
                </Typography>
            </LegalSection>

            <LegalSection title="What we handle">
                <LegalList>
                    <LegalListItem>
                        <strong>Public game data.</strong> Minecraft usernames and
                        UUIDs, and the statistics the Hypixel API publishes for those
                        accounts. We store snapshots of this data, with the time we
                        retrieved them, for the players that get looked up.
                    </LegalListItem>
                    <LegalListItem>
                        <strong>A client identifier.</strong> A random ID that your
                        browser or your copy of the overlay generates and stores
                        locally. It is not derived from your account or your device.
                    </LegalListItem>
                    <LegalListItem>
                        <strong>Technical request data.</strong> Your IP address, which
                        our database stores only as a hash, and the client version
                        string.
                    </LegalListItem>
                    <LegalListItem>
                        <strong>Diagnostics.</strong> Error reports from the website and
                        the backend, which may include the client identifier and
                        technical details of the request.
                    </LegalListItem>
                    <LegalListItem>
                        <strong>Sign-in details.</strong> Where a feature asks you to
                        sign in, the identifiers the sign-in provider gives us for it.
                    </LegalListItem>
                </LegalList>
                <Typography variant="body1">
                    We never ask you for your name, email address, payment details or
                    location.
                </Typography>
            </LegalSection>

            <LegalSection title="Why we handle it">
                <Typography variant="body1">
                    To provide the service and the statistics history it is built on, to
                    apply rate limits and protect the service from abuse, and to find
                    and fix faults. Where the GDPR applies, we do this on the basis of
                    our legitimate interest in operating the service.
                </Typography>
            </LegalSection>

            <LegalSection title="What stays on your computer">
                <LegalList>
                    <LegalListItem>
                        The overlay reads your Minecraft log file to see which players
                        are in your game. The file never leaves your computer — only the
                        usernames and UUIDs found in it are sent, to look them up.
                    </LegalListItem>
                    <LegalListItem>
                        The overlay keeps its settings, including nicknames and any API
                        keys you enter, in a file on your computer. We never receive
                        that file.
                    </LegalListItem>
                    <LegalListItem>
                        Discord Rich Presence is on by default: when Discord is running,
                        the overlay tells your Discord client what you are playing. You
                        can change or turn this off in the overlay&apos;s settings.
                    </LegalListItem>
                </LegalList>
            </LegalSection>

            <LegalSection title="What we do not do">
                <Typography variant="body1">
                    We use no advertising, no cross-site tracking and no third-party
                    analytics, and we do not sell or rent your data. The website uses
                    browser storage only for what it needs to work, such as your
                    settings and the client identifier.
                </Typography>
            </LegalSection>

            <LegalSection title="Third parties">
                <Typography variant="body1">
                    We use other services to run Prism Overlay and to get the data it
                    shows. They include:
                </Typography>
                <LegalList>
                    <LegalListItem>
                        <strong>Hypixel API</strong> — the source of the player
                        statistics. Queried by UUID.
                    </LegalListItem>
                    <LegalListItem>
                        <strong>Mojang API</strong> — resolves usernames to UUIDs and
                        back.
                    </LegalListItem>
                    <LegalListItem>
                        <strong>Urchin</strong> — returns cheating and sniping tags for
                        a player. Queried by UUID.
                    </LegalListItem>
                    <LegalListItem>
                        <strong>Google Cloud</strong> — hosts the backend and the
                        database, and logs requests to it.
                    </LegalListItem>
                    <LegalListItem>
                        <strong>Sentry</strong> — receives the diagnostics.
                    </LegalListItem>
                </LegalList>
                <Typography variant="body1">
                    We send them no more than the request needs. They may handle the
                    data outside your country.
                </Typography>
            </LegalSection>

            <LegalSection title="How long we keep it">
                <Typography variant="body1">
                    Statistics snapshots are kept indefinitely. Everything else is kept
                    for as long as we need it to run the service. Diagnostics expire on
                    our providers&apos; own schedules.
                </Typography>
            </LegalSection>

            <LegalSection title="Your rights">
                <LegalList>
                    <LegalListItem>
                        Ask us to delete the statistics stored for your Minecraft
                        account.
                    </LegalListItem>
                    <LegalListItem>
                        Reset your client identifier by clearing this site&apos;s data
                        in your browser, or by deleting the overlay&apos;s settings
                        file.
                    </LegalListItem>
                    <LegalListItem>
                        Where the GDPR or a similar law applies, request access to,
                        correction of, or deletion of your personal data, restrict or
                        object to how we handle it, and complain to your data protection
                        authority.
                    </LegalListItem>
                </LegalList>
                <Typography variant="body1">
                    To exercise any of this, ask on <DiscordLink />.
                </Typography>
            </LegalSection>

            <LegalSection title="Children">
                <Typography variant="body1">
                    Prism Overlay is not directed at children under 13, and we do not
                    knowingly collect personal information from them. If you believe we
                    hold something we should not, contact us on <DiscordLink />.
                </Typography>
            </LegalSection>

            <LegalSection title="Changes">
                <Typography variant="body1">
                    We may update this policy. The date above shows the current version.
                </Typography>
            </LegalSection>

            <LegalSection title="Contact">
                <Typography variant="body1">
                    Ask on <DiscordLink />. See also the{" "}
                    <Link to="/terms">terms of service</Link>.
                </Typography>
            </LegalSection>
        </LegalPage>
    );
}

export const Route = createFileRoute("/privacy")({
    component: RouteComponent,
});
