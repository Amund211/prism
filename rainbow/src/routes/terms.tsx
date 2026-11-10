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
            title="Terms of service"
            lastUpdated={LAST_UPDATED}
            path="/terms"
            description="The terms for using Prism Overlay: a free service, provided as is, with no affiliation to Mojang Studios, Microsoft or The Hypixel Network."
        >
            <LegalSection title="Scope">
                <Typography variant="body1">
                    These terms govern use of Prism Overlay: the overlay application,
                    the website at prismoverlay.com, and the backend API that serves
                    them. By using any of them, you accept these terms. If you do not
                    accept them, do not use the service.
                </Typography>
            </LegalSection>

            <LegalSection title="No affiliation">
                <Typography variant="body1">
                    Prism Overlay is an independent project. It is not associated with,
                    endorsed by or sponsored by Mojang Studios, Microsoft or The Hypixel
                    Network. Minecraft is a trademark of Mojang Studios. Where the name{" "}
                    <strong>Prism Overlay</strong> appears on a third-party screen, it
                    refers to this project only.
                </Typography>
            </LegalSection>

            <LegalSection title="Free service, no guarantees">
                <Typography variant="body1">
                    The service is free. We give no guarantee of availability, and we
                    may change, suspend or discontinue any part of it, and delete stored
                    data, at any time and without notice.
                </Typography>
            </LegalSection>

            <LegalSection title="Acceptable use">
                <LegalList>
                    <LegalListItem>
                        Use the backend only through the clients we publish. Do not
                        connect other software to it.
                    </LegalListItem>
                    <LegalListItem>
                        Do not circumvent rate limits, authentication or any other
                        restriction.
                    </LegalListItem>
                    <LegalListItem>
                        Do not scrape, bulk-download or redistribute data from the
                        service.
                    </LegalListItem>
                    <LegalListItem>
                        Do not use the service to harass or target anyone, or for any
                        unlawful purpose.
                    </LegalListItem>
                </LegalList>
                <Typography variant="body1">
                    We may limit, suspend or withdraw access for any client, session or
                    user at any time and without notice.
                </Typography>
            </LegalSection>

            <LegalSection title="Other services">
                <Typography variant="body1">
                    You must follow the rules of the services you use Prism Overlay
                    with, including the Minecraft EULA, the rules and{" "}
                    <a
                        href="https://developer.hypixel.net/policies/"
                        target="_blank"
                        rel="noreferrer"
                    >
                        API policy
                    </a>{" "}
                    of The Hypixel Network, and Discord&apos;s terms. We cannot grant
                    permission on their behalf.
                </Typography>
            </LegalSection>

            <LegalSection title="Accounts">
                <Typography variant="body1">
                    Some features may require you to sign in with a third-party account.
                    You are responsible for that account and for what happens through
                    it.
                </Typography>
            </LegalSection>

            <LegalSection title="No warranty">
                <Typography variant="body1">
                    The service is provided <strong>as is</strong> and{" "}
                    <strong>as available</strong>, without warranty of any kind, express
                    or implied, including any implied warranty of merchantability,
                    fitness for a particular purpose or non-infringement. We do not
                    warrant that the statistics shown are accurate, current or complete.
                </Typography>
            </LegalSection>

            <LegalSection title="Limitation of liability">
                <Typography variant="body1">
                    To the maximum extent permitted by law, we are not liable for any
                    indirect, incidental, special or consequential damages, or for any
                    loss of data, accounts or game progress, arising from your use of,
                    or inability to use, the service. Nothing in these terms limits
                    liability that the law does not allow to be limited.
                </Typography>
            </LegalSection>

            <LegalSection title="Source code">
                <Typography variant="body1">
                    The overlay and the backend are published under the{" "}
                    <a
                        href="https://www.gnu.org/licenses/agpl-3.0.html"
                        target="_blank"
                        rel="noreferrer"
                    >
                        GNU AGPL v3
                    </a>{" "}
                    on{" "}
                    <a
                        href="https://github.com/Amund211/prism"
                        target="_blank"
                        rel="noreferrer"
                    >
                        GitHub
                    </a>
                    . That licence governs the code; these terms govern the service we
                    host.
                </Typography>
            </LegalSection>

            <LegalSection title="Changes">
                <Typography variant="body1">
                    We may update these terms. The date above shows the current version.
                    If you keep using the service after a change, you accept the new
                    terms.
                </Typography>
            </LegalSection>

            <LegalSection title="Contact">
                <Typography variant="body1">
                    Data handling is described in the{" "}
                    <Link to="/privacy">privacy policy</Link>. For anything else, ask on{" "}
                    <DiscordLink />.
                </Typography>
            </LegalSection>
        </LegalPage>
    );
}

export const Route = createFileRoute("/terms")({
    component: RouteComponent,
});
