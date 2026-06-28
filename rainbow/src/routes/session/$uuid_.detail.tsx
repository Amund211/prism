import {
    AutoAwesome,
    Bed,
    Block,
    Bolt,
    Cloud,
    ContentCopy,
    DirectionsRun,
    EmojiEvents,
    Group,
    HeartBroken,
    Help,
    Info,
    IosShare,
    LocalFireDepartment,
    MilitaryTech,
    Schedule,
    Shield,
    Speed,
    SportsEsports,
    Star,
    StopCircle,
    TrendingDown,
    TrendingFlat,
    TrendingUp,
    Verified,
    WorkspacePremium,
} from "@mui/icons-material";
import type { SvgIconComponent } from "@mui/icons-material";
import {
    Alert,
    Box,
    Button,
    Chip,
    LinearProgress,
    Skeleton,
    Snackbar,
    Stack,
    Tooltip,
    Typography,
    useTheme,
} from "@mui/material";
import { alpha } from "@mui/material/styles";
import type { Palette, Theme } from "@mui/material/styles";
import { captureException } from "@sentry/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Navigate } from "@tanstack/react-router";
import React from "react";
import {
    Area,
    CartesianGrid,
    ComposedChart,
    Line,
    Tooltip as ChartTooltip,
    XAxis,
    YAxis,
} from "recharts";

import { PlayerHead } from "#components/player.tsx";
import { TrendIcon } from "#components/TrendIcon.tsx";
import { formatDuration } from "#helpers/duration.ts";
import type {
    GameAccoladeKind,
    Milestone,
    ModeBreakdownKey,
    ModeStats,
    SegmentGameNumber,
    SessionAggregate,
    SessionTagKey,
} from "#helpers/sessionDetail.ts";
import {
    aggregate,
    bestGame,
    computeMilestones,
    fastestWin,
    fkdrTrajectory,
    fkdrVsLifetime,
    GAMEMODES,
    gameAccolade,
    gameNumberLabel,
    inferredGameCount,
    modeBreakdown,
    segmentDurationMs,
    segmentExperience,
    segmentGameNumbers,
    sessionTagKeys,
    statDelta,
    trailingStreak,
} from "#helpers/sessionDetail.ts";
import { normalizeUUID } from "#helpers/uuid.ts";
import type {
    GameOutcome,
    GameResult,
    GameSegment,
    SessionAt,
} from "#queries/sessionAt.ts";
import { getSessionAtQueryOptions } from "#queries/sessionAt.ts";
import { useUUIDToUsername } from "#queries/username.ts";
import { detailSearchSchema } from "#schemas/detailSearch.ts";
import {
    formatStatValue,
    getTrendDirection,
    getTrendSentiment,
} from "#stats/format.ts";
import type { TrendSentiment } from "#stats/format.ts";
import type { StatKey } from "#stats/keys.ts";
import { getGamemodeLabel, getShortStatLabel } from "#stats/labels.ts";
import { bedwarsLevelFromExp } from "#stats/stars.ts";
import { rainbowGradient } from "#theme/tokens.ts";
import { MS_PER_HOUR, MS_PER_MINUTE } from "#time.ts";

export const Route = createFileRoute("/session/$uuid_/detail")({
    validateSearch: detailSearchSchema,
    // oxlint-disable-next-line eslint/no-use-before-define
    component: RouteComponent,
});

const MILESTONE_ICONS: Record<Milestone["key"], SvgIconComponent> = {
    prestige: AutoAwesome,
    wins: EmojiEvents,
    fkdr: TrendingUp,
};

// The stat each milestone tracks, so its current→target trend can be coloured
// with the app's shared sentiment logic (all three are "higher is better").
const MILESTONE_STAT: Record<Milestone["key"], StatKey> = {
    prestige: "stars",
    wins: "wins",
    fkdr: "fkdr",
};

interface SessionTag {
    readonly key: SessionTagKey;
    readonly label: string;
    readonly icon: SvgIconComponent;
    readonly tooltip: string;
}

// Dress each earned badge (see sessionTagKeys) with an icon, label and tooltip.
// The eligibility logic lives in the helper; this only handles presentation.
const computeTags = (agg: SessionAggregate): SessionTag[] =>
    sessionTagKeys(agg).map((key): SessionTag => {
        switch (key) {
            case "flawless": {
                return {
                    key,
                    label: "Flawless",
                    icon: Verified,
                    tooltip: "No losses and no final deaths this session",
                };
            }
            case "perfect": {
                return {
                    key,
                    label: "Perfect run",
                    icon: WorkspacePremium,
                    tooltip: "Won every game this session",
                };
            }
            case "on_fire": {
                return {
                    key,
                    label: "On fire",
                    icon: LocalFireDepartment,
                    tooltip: `${formatStatValue("fkdr", agg.fkdr)} session FKDR vs ${formatStatValue("fkdr", agg.lifetimeFkdr)} lifetime`,
                };
            }
            case "marathon": {
                return {
                    key,
                    label: "Marathon",
                    icon: DirectionsRun,
                    tooltip: `${(agg.elapsedMs / MS_PER_HOUR).toFixed(1)} hours played`,
                };
            }
        }
    });

// Accent colours for the auto-derived tags. Pulled from the theme rather than
// hand-picked hex: semantic tokens where a tag has an obvious mood (flawless =
// warning gold, perfect = win green) and rainbow/secondary accents otherwise.
const tagColor = (
    // oxlint-disable-next-line typescript/prefer-readonly-parameter-types
    theme: Theme,
    key: SessionTagKey,
): string => {
    switch (key) {
        case "flawless": {
            return theme.palette.warning.main;
        }
        case "perfect": {
            return theme.palette.success.main;
        }
        case "on_fire": {
            return theme.palette.rainbow[0];
        }
        case "marathon": {
            return theme.palette.secondary.main;
        }
    }
};

const milestoneColor = (
    // oxlint-disable-next-line typescript/prefer-readonly-parameter-types
    theme: Theme,
    key: Milestone["key"],
): string => {
    switch (key) {
        case "prestige": {
            return theme.palette.secondary.main;
        }
        case "wins": {
            return theme.palette.success.main;
        }
        case "fkdr": {
            return theme.palette.info.main;
        }
    }
};

const OUTCOME_LABEL: Record<GameOutcome, string> = {
    win: "W",
    loss: "L",
    draw: "D",
};

const OUTCOME_FULL_LABEL: Record<GameOutcome, string> = {
    win: "WIN",
    loss: "LOSS",
    draw: "DRAW",
};

// Why a window can have unattributable games — mirrors the session-list copy.
const TRACKING_NOTE =
    'The Prism Overlay only records games when the player is using it with "Online Game Stats" enabled in their Hypixel settings.';

// win → success green, loss → error red, draw → neutral (rare, neither good nor bad).
const outcomeColor = (
    // oxlint-disable-next-line typescript/prefer-readonly-parameter-types
    theme: Theme,
    outcome: GameOutcome,
): string => {
    switch (outcome) {
        case "win": {
            return theme.palette.success.main;
        }
        case "loss": {
            return theme.palette.error.main;
        }
        case "draw": {
            return theme.palette.text.secondary;
        }
    }
};

const Panel: React.FC<{ children: React.ReactNode; sx?: object }> = ({
    children,
    sx,
}) => (
    <Box
        sx={{
            bgcolor: "background.paper",
            border: 1,
            borderColor: "divider",
            borderRadius: 1.5,
            p: 2.5,
            ...sx,
        }}
    >
        {children}
    </Box>
);

const NoSession: React.FC<{ username: string }> = ({ username }) => (
    <Box
        sx={{
            borderRadius: 1.5,
            border: 1,
            borderColor: "divider",
            p: 4,
            textAlign: "center",
        }}
    >
        <Info color="info" fontSize="large" />
        <Typography variant="h6" sx={{ mt: 1 }}>
            No session yet
        </Typography>
        <Typography variant="body2" color="textSecondary" sx={{ mt: 1 }}>
            {`${username} has no recorded session overlapping this date. Come back after they've played a game with the Prism Overlay running.`}
        </Typography>
    </Box>
);

const EndedBadge: React.FC = () => (
    <Chip
        icon={<StopCircle sx={{ fontSize: 12 }} />}
        label="ENDED"
        size="small"
        sx={{
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: 1,
            color: "text.secondary",
            bgcolor: "action.hover",
        }}
    />
);

const LiveBadge: React.FC = () => (
    <Chip
        label="LIVE"
        size="small"
        sx={{
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: 1,
            color: "success.main",
            bgcolor: (theme) => alpha(theme.palette.success.main, 0.12),
            "& .MuiChip-label": {
                pl: 1.5,
                position: "relative",
                "&::before": {
                    content: '""',
                    position: "absolute",
                    left: 4,
                    top: "50%",
                    transform: "translateY(-50%)",
                    width: 6,
                    height: 6,
                    borderRadius: "50%",
                    bgcolor: "success.main",
                    animation: "rbw-pulse 1.6s ease-in-out infinite",
                },
            },
            "@keyframes rbw-pulse": {
                "0%, 100%": { opacity: 1, transform: "translateY(-50%) scale(1)" },
                "50%": { opacity: 0.4, transform: "translateY(-50%) scale(1.3)" },
            },
        }}
    />
);

interface PlayerBannerProps {
    uuid: string;
    username: string;
    session: NonNullable<SessionAt["session"]>;
    agg: SessionAggregate;
    onShare: () => void;
}

const PlayerBanner: React.FC<PlayerBannerProps> = ({
    uuid,
    username,
    session,
    agg,
    onShare,
}) => {
    const stars = Math.floor(bedwarsLevelFromExp(session.end.experience));
    const startedAt = session.start.queriedAt;
    const endedAt = session.end.queriedAt;
    const startedDate = startedAt.toLocaleDateString(undefined, {
        dateStyle: "medium",
    });
    const startedTime = startedAt.toLocaleTimeString(undefined, {
        timeStyle: "short",
    });
    const endedTime = endedAt.toLocaleTimeString(undefined, {
        timeStyle: "short",
    });
    return (
        <Box
            sx={{
                position: "relative",
                bgcolor: "background.paper",
                border: 1,
                borderColor: "divider",
                borderRadius: 1.5,
                p: 3,
                overflow: "hidden",
            }}
        >
            <Box
                sx={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    right: 0,
                    height: 3,
                    background: rainbowGradient(),
                }}
            />
            <Stack
                direction={{ xs: "column", sm: "row" }}
                alignItems={{ xs: "stretch", sm: "center" }}
                gap={2}
            >
                <PlayerHead uuid={uuid} username={username} variant="face" width={64} />
                <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Stack
                        direction="row"
                        alignItems="center"
                        gap={1.5}
                        flexWrap="wrap"
                    >
                        <Chip
                            icon={<Star sx={{ color: "secondary.main" }} />}
                            label={stars}
                            size="small"
                            sx={{
                                color: "secondary.main",
                                bgcolor: (theme) =>
                                    alpha(theme.palette.secondary.main, 0.12),
                                fontFamily: "monospace",
                            }}
                        />
                        <Typography variant="h5">{username}</Typography>
                        {session.ongoing ? <LiveBadge /> : <EndedBadge />}
                    </Stack>
                    <Stack
                        direction="row"
                        gap={3}
                        flexWrap="wrap"
                        sx={{ mt: 1 }}
                        color="text.secondary"
                    >
                        <Stack direction="row" alignItems="center" gap={0.5}>
                            <Schedule fontSize="small" />
                            <Typography variant="body2">
                                {`${startedDate} · ${startedTime}–${endedTime} · ${formatDuration(agg.elapsedMs)}`}
                            </Typography>
                        </Stack>
                        <Stack direction="row" alignItems="center" gap={0.5}>
                            <SportsEsports fontSize="small" />
                            <Typography variant="body2">
                                {`${agg.games.toString()} games`}
                            </Typography>
                        </Stack>
                    </Stack>
                </Box>
                <Button
                    variant="outlined"
                    startIcon={<IosShare />}
                    onClick={onShare}
                    sx={{ alignSelf: { xs: "flex-start", sm: "center" } }}
                >
                    Share
                </Button>
            </Stack>
        </Box>
    );
};

const TagsRow: React.FC<{ tags: readonly SessionTag[] }> = ({ tags }) => {
    const theme = useTheme();
    return (
        <Stack direction="row" gap={1} flexWrap="wrap">
            {tags.map((tag) => {
                const Icon = tag.icon;
                const color = tagColor(theme, tag.key);
                return (
                    <Tooltip key={tag.key} title={tag.tooltip}>
                        <Chip
                            icon={<Icon sx={{ color: `${color} !important` }} />}
                            label={tag.label}
                            size="small"
                            sx={{
                                color,
                                bgcolor: alpha(color, 0.08),
                                border: 1,
                                borderColor: alpha(color, 0.33),
                                fontWeight: 600,
                                letterSpacing: 0.3,
                            }}
                        />
                    </Tooltip>
                );
            })}
        </Stack>
    );
};

// Dotted MUI palette colour paths (e.g. "success.main"), validated against the
// theme so a typo like "sucess.main" fails to compile.
type ThemeColor = {
    [K in keyof Palette]: Palette[K] extends (...args: readonly never[]) => unknown
        ? never
        : Palette[K] extends object
          ? `${K & string}.${keyof Palette[K] & string}`
          : never;
}[keyof Palette];

// Delta/trend sentiment → theme colour (flat/neutral = muted). Shared by the
// delta tags and the milestones card; the arrow icon comes from the shared
// TREND_ICON map.
const SENTIMENT_COLOR: Record<TrendSentiment, ThemeColor> = {
    good: "success.main",
    bad: "error.main",
    neutral: "text.disabled",
};

const DeltaTag: React.FC<{
    value: number;
    suffix?: string;
    stat: StatKey;
}> = ({ value, suffix = "", stat }) => {
    const direction = getTrendDirection(0, value);
    const sentiment = getTrendSentiment(stat, direction);
    const sign = direction === "up" ? "+" : "";
    return (
        <Stack
            direction="row"
            alignItems="center"
            gap={0.5}
            component="span"
            sx={{ color: SENTIMENT_COLOR[sentiment] }}
        >
            <TrendIcon direction={direction} sx={{ fontSize: 14 }} />
            <span>{`${sign}${value.toFixed(2)}${suffix} vs lifetime`}</span>
        </Stack>
    );
};

interface KpiCardProps {
    label: string;
    value: string;
    sub: React.ReactNode;
    accentColor?: string;
}

const KpiCard: React.FC<KpiCardProps> = ({ label, value, sub, accentColor }) => (
    <Panel sx={{ p: 2 }}>
        <Typography
            variant="caption"
            sx={{
                color: "text.secondary",
                textTransform: "uppercase",
                letterSpacing: 0.8,
            }}
        >
            {label}
        </Typography>
        <Typography
            sx={{
                fontSize: 30,
                fontWeight: 400,
                lineHeight: 1,
                mt: 1,
                mb: 0.75,
                color: accentColor ?? "text.primary",
            }}
        >
            {value}
        </Typography>
        <Typography variant="body2" color="textSecondary" component="div">
            {sub}
        </Typography>
    </Panel>
);

const KPIRow: React.FC<{ agg: SessionAggregate }> = ({ agg }) => {
    const fkdrDelta = agg.fkdr - agg.lifetimeFkdr;
    const wrDelta = (agg.winRate - agg.lifetimeWR) * 100;
    return (
        <Box
            sx={{
                display: "grid",
                gridTemplateColumns: { xs: "repeat(2, 1fr)", sm: "repeat(4, 1fr)" },
                gap: 1.5,
            }}
        >
            <KpiCard
                label="Games"
                value={agg.games.toString()}
                sub={`${agg.wins.toString()}W · ${agg.losses.toString()}L`}
            />
            <KpiCard
                label="Win rate"
                value={formatStatValue("winrate", agg.winRate)}
                sub={<DeltaTag value={wrDelta} suffix="%" stat="winrate" />}
                accentColor="success.main"
            />
            <KpiCard
                label="Session FKDR"
                value={formatStatValue("fkdr", agg.fkdr)}
                sub={<DeltaTag value={fkdrDelta} stat="fkdr" />}
                accentColor="primary.main"
            />
            <KpiCard
                label="Stars gained"
                value={`+${formatStatValue("stars", agg.stars)}`}
                sub={`${(agg.xp / 1000).toFixed(1)}k XP`}
                accentColor="secondary.main"
            />
        </Box>
    );
};

interface GameAccolade {
    readonly icon: SvgIconComponent;
    readonly color: string;
    readonly label: string;
    readonly tooltip: string;
}

// Icon/colour/label for a won-game accolade (the decision itself lives in the
// gameAccolade helper). Shown icon-only on the tile and repeated as a labelled
// chip in the expanded detail.
const accoladePresentation = (
    // oxlint-disable-next-line typescript/prefer-readonly-parameter-types
    theme: Theme,
    kind: GameAccoladeKind,
): GameAccolade => {
    switch (kind) {
        case "perfect": {
            return {
                icon: MilitaryTech,
                color: theme.palette.secondary.main,
                label: "Perfect game",
                tooltip: "Got every final kill and every enemy bed in the game.",
            };
        }
        case "carried": {
            return {
                icon: Group,
                color: theme.palette.info.main,
                label: "Carried",
                tooltip: "Won after taking a final death.",
            };
        }
        case "clutch": {
            return {
                icon: Shield,
                color: theme.palette.warning.main,
                label: "Clutch",
                tooltip: "Won after losing their bed.",
            };
        }
    }
};

// Resolve a game's accolade to its presentation, or null when it has none.
const gameAccoladeView = (
    // oxlint-disable-next-line typescript/prefer-readonly-parameter-types
    theme: Theme,
    game: GameResult,
): GameAccolade | null => {
    const kind = gameAccolade(game);
    return kind === null ? null : accoladePresentation(theme, kind);
};

// Rounded outline pill flagging what happened in the game (final death vs
// survived, bed lost vs kept, or the won-game accolade). An optional tooltip
// wraps the pill — the Stack forwards refs so MUI Tooltip anchors to it.
const StatusPill: React.FC<{
    icon: SvgIconComponent;
    label: string;
    color: string;
    tooltip?: string;
}> = ({ icon: Icon, label, color, tooltip }) => {
    const pill = (
        <Stack
            direction="row"
            alignItems="center"
            gap={0.5}
            sx={{
                px: 1,
                py: 0.25,
                borderRadius: 5,
                border: 1,
                borderColor: alpha(color, 0.4),
                bgcolor: alpha(color, 0.08),
                color,
            }}
        >
            <Icon sx={{ fontSize: 14 }} />
            <Typography variant="caption" sx={{ fontWeight: 600 }}>
                {label}
            </Typography>
        </Stack>
    );
    return tooltip === undefined ? pill : <Tooltip title={tooltip}>{pill}</Tooltip>;
};

const GameDetail: React.FC<{ segment: GameSegment; numbering: SegmentGameNumber }> = ({
    segment,
    numbering,
}) => {
    const theme = useTheme();
    const xp = segmentExperience(segment);
    const durationLabel = formatDuration(segmentDurationMs(segment));
    // Same running-game-count label the strip tile shows (e.g. "G3", "G5-7").
    const numberLabel = gameNumberLabel(numbering);

    // Header context line + optional outcome badge + status pills + stat grid,
    // derived per segment kind (real game / no-game window / multi-game gap).
    let title: string;
    let context: string;
    let badge: { label: string; color: string } | null = null;
    let pills: React.ReactNode = null;
    let items: [string, string][];

    if (segment.game === null) {
        const count = inferredGameCount(segment);
        if (count === 0) {
            title = "Segment";
            context = "No game";
            items = [
                ["GAMES", "0"],
                ["XP", `+${xp.toLocaleString()}`],
                ["SPAN", durationLabel],
            ];
        } else {
            const delta = statDelta(segment.start.overall, segment.end.overall);
            title = numberLabel ?? "Games";
            context = `${count.toString()} game${count === 1 ? "" : "s"}`;
            items = [
                ["FINAL KILLS", delta.fk.toString()],
                ["BEDS BROKEN", delta.bb.toString()],
                ["KILLS / DEATHS", `${delta.k.toString()} / ${delta.d.toString()}`],
                ["XP", `+${xp.toLocaleString()}`],
            ];
        }
    } else {
        const { game } = segment;
        title = numberLabel ?? "Game";
        context = getGamemodeLabel(game.gamemode, true);
        badge = {
            label: OUTCOME_FULL_LABEL[game.outcome],
            color: outcomeColor(theme, game.outcome),
        };
        const accolade = gameAccoladeView(theme, game);
        pills = (
            <>
                {accolade !== null && (
                    <StatusPill
                        icon={accolade.icon}
                        label={accolade.label}
                        color={accolade.color}
                        tooltip={accolade.tooltip}
                    />
                )}
                {game.finalDeath ? (
                    <StatusPill
                        icon={HeartBroken}
                        label="Final death"
                        color={theme.palette.error.main}
                        tooltip="Player took a final death this game."
                    />
                ) : (
                    <StatusPill
                        icon={Shield}
                        label="Survived"
                        color={theme.palette.success.main}
                        tooltip="Player did not take a final death this game."
                    />
                )}
                {game.bedLost ? (
                    <StatusPill
                        icon={Bed}
                        label="Bed lost"
                        color={theme.palette.error.main}
                        tooltip="Player's bed was broken this game."
                    />
                ) : (
                    <StatusPill
                        icon={Bed}
                        label="Bed kept"
                        color={theme.palette.success.main}
                        tooltip="Player's bed was not broken this game."
                    />
                )}
            </>
        );
        items = [
            ["FINAL KILLS", game.finalKills.toString()],
            ["BEDS BROKEN", game.bedsBroken.toString()],
            ["KILLS / DEATHS", `${game.kills.toString()} / ${game.deaths.toString()}`],
            ["XP", `+${game.experience.toLocaleString()}`],
        ];
    }

    return (
        <Box sx={{ mt: 1.75, pt: 1.75, borderTop: 1, borderColor: "divider" }}>
            <Stack
                direction="row"
                justifyContent="space-between"
                alignItems="center"
                flexWrap="wrap"
                gap={1}
                sx={{ mb: 1.75, maxWidth: 720, mx: "auto" }}
            >
                <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap">
                    <Typography sx={{ fontWeight: 600 }}>{title}</Typography>
                    <Typography variant="body2" color="textSecondary">
                        {`· ${context} · ${durationLabel}`}
                    </Typography>
                    {badge !== null && (
                        <Typography
                            component="span"
                            sx={{
                                px: 0.875,
                                py: 0.25,
                                borderRadius: 0.75,
                                bgcolor: alpha(badge.color, 0.15),
                                color: badge.color,
                                fontSize: 11,
                                fontWeight: 700,
                                letterSpacing: 0.5,
                            }}
                        >
                            {badge.label}
                        </Typography>
                    )}
                </Stack>
                {pills !== null && (
                    <Stack direction="row" gap={1} flexWrap="wrap">
                        {pills}
                    </Stack>
                )}
            </Stack>
            <Box
                sx={{
                    display: "grid",
                    gridTemplateColumns: "repeat(4, 1fr)",
                    gap: 1,
                    maxWidth: 720,
                    mx: "auto",
                }}
            >
                {items.map(([label, value]) => (
                    <Box key={label}>
                        <Typography
                            variant="caption"
                            color="textSecondary"
                            sx={{
                                textTransform: "uppercase",
                                letterSpacing: 0.6,
                                fontSize: 10,
                            }}
                        >
                            {label}
                        </Typography>
                        <Typography
                            sx={{ fontFamily: "monospace", fontSize: 16, mt: 0.5 }}
                        >
                            {value}
                        </Typography>
                    </Box>
                ))}
            </Box>
        </Box>
    );
};

// Icon-only badge shown left of the W/L chip on a game tile — the same
// accolade that the expanded detail repeats as a labelled chip.
const ClutchOrCarriedBadge: React.FC<{ game: GameResult }> = ({ game }) => {
    const theme = useTheme();
    const accolade = gameAccoladeView(theme, game);
    if (accolade === null) return null;
    const Icon = accolade.icon;
    return (
        <Tooltip title={`${accolade.label} — ${accolade.tooltip}`}>
            <Box
                aria-label={accolade.label}
                sx={{
                    width: 18,
                    height: 18,
                    borderRadius: 0.75,
                    bgcolor: alpha(accolade.color, 0.12),
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                }}
            >
                <Icon sx={{ fontSize: 12, color: accolade.color }} />
            </Box>
        </Tooltip>
    );
};

const GameTile: React.FC<{
    segment: GameSegment;
    numbering: SegmentGameNumber;
    active: boolean;
    onClick: () => void;
}> = ({ segment, numbering, active, onClick }) => {
    const theme = useTheme();
    const { game } = segment;
    const durationMs = segmentDurationMs(segment);
    const mins = Math.max(1, Math.round(durationMs / MS_PER_MINUTE));
    // Running-game-count label (e.g. "G3", "G5-7"); null for a no-game window.
    const numberLabel = gameNumberLabel(numbering);

    if (game === null) {
        const count = inferredGameCount(segment);
        const noGame = count === 0;
        const color = noGame ? theme.palette.textMuted : theme.palette.text.secondary;
        const gapTooltip =
            count === 1
                ? `This game couldn't be attributed individually. ${TRACKING_NOTE}`
                : `These ${count.toString()} games couldn't be attributed individually. ${TRACKING_NOTE}`;
        const helpTooltip = noGame
            ? `No game was attributed to this window. ${TRACKING_NOTE}`
            : gapTooltip;
        const gamesLabel = count === 1 ? "game" : "games";
        return (
            <Button
                onClick={onClick}
                aria-expanded={active}
                sx={{
                    px: 1.5,
                    py: 1.25,
                    borderRadius: 1.25,
                    bgcolor: active ? alpha(color, 0.13) : "action.hover",
                    border: 1,
                    // Use a muted version of the tile colour (not the faint
                    // `divider`) so the dashed border reads as dashed at rest —
                    // otherwise the dashes only become visible once selected.
                    borderColor: active ? color : alpha(color, 0.5),
                    borderStyle: "dashed",
                    color: "text.primary",
                    textTransform: "none",
                    textAlign: "left",
                    flexDirection: "column",
                    alignItems: "stretch",
                    position: "relative",
                    overflow: "hidden",
                    minWidth: 0,
                    "&:hover": { bgcolor: alpha(color, 0.07) },
                }}
            >
                <Stack
                    direction="row"
                    alignItems="center"
                    justifyContent="space-between"
                    sx={{ mb: 0.5 }}
                >
                    <Typography variant="caption" sx={{ fontFamily: "monospace" }}>
                        {numberLabel ?? ""}
                    </Typography>
                    <Tooltip title={helpTooltip}>
                        <Help sx={{ fontSize: 14, color }} />
                    </Tooltip>
                </Stack>
                <Typography sx={{ fontSize: 18, lineHeight: 1, fontWeight: 500 }}>
                    {noGame ? "—" : count.toString()}
                </Typography>
                <Typography variant="caption" color="textSecondary">
                    {noGame ? "no game" : gamesLabel}
                </Typography>
                <Stack direction="row" gap={0.75} sx={{ mt: 1, fontSize: 10 }}>
                    <Typography variant="caption" color="textSecondary">
                        ?
                    </Typography>
                    <Typography variant="caption" sx={{ ml: "auto" }}>
                        {`${mins.toString()}m`}
                    </Typography>
                </Stack>
            </Button>
        );
    }

    const color = outcomeColor(theme, game.outcome);
    return (
        <Button
            onClick={onClick}
            aria-expanded={active}
            sx={{
                px: 1.5,
                py: 1.25,
                borderRadius: 1.25,
                bgcolor: active ? alpha(color, 0.13) : "action.hover",
                border: 1,
                borderColor: active ? color : "divider",
                color: "text.primary",
                textTransform: "none",
                textAlign: "left",
                flexDirection: "column",
                alignItems: "stretch",
                position: "relative",
                overflow: "hidden",
                minWidth: 0,
                "&:hover": { bgcolor: alpha(color, 0.07) },
            }}
        >
            <Box
                sx={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    right: 0,
                    height: 3,
                    bgcolor: color,
                }}
            />
            <Stack
                direction="row"
                alignItems="center"
                justifyContent="space-between"
                sx={{ mb: 0.5 }}
            >
                <Typography variant="caption" sx={{ fontFamily: "monospace" }}>
                    {numberLabel ?? ""}
                </Typography>
                <Stack direction="row" alignItems="center" gap={0.5}>
                    <ClutchOrCarriedBadge game={game} />
                    <Chip
                        size="small"
                        label={OUTCOME_LABEL[game.outcome]}
                        sx={{
                            height: 18,
                            fontSize: 10,
                            fontWeight: 600,
                            color,
                            bgcolor: alpha(color, 0.12),
                        }}
                    />
                </Stack>
            </Stack>
            <Typography sx={{ fontSize: 18, lineHeight: 1, fontWeight: 500 }}>
                {game.finalKills.toString()}
            </Typography>
            <Typography variant="caption" color="textSecondary">
                {game.finalKills === 1 ? "Final" : "Finals"}
            </Typography>
            <Stack direction="row" gap={0.75} sx={{ mt: 1, fontSize: 10 }}>
                <Box sx={{ color: theme.palette.gamemode[game.gamemode] }}>●</Box>
                <Typography variant="caption">
                    {getGamemodeLabel(game.gamemode, true)}
                </Typography>
                <Typography variant="caption" sx={{ ml: "auto" }}>
                    {`${mins.toString()}m`}
                </Typography>
            </Stack>
        </Button>
    );
};

const StreakIndicator: React.FC<{ segments: readonly GameSegment[] }> = ({
    segments,
}) => {
    const theme = useTheme();
    const streak = trailingStreak(segments);
    // Draws don't form a meaningful streak to surface, so only win/loss runs show.
    if (streak === null || streak.outcome === "draw") return null;
    const won = streak.outcome === "win";
    const color = won ? theme.palette.success.main : theme.palette.error.main;
    const Icon = won ? LocalFireDepartment : Cloud;
    const label = `${streak.length.toString()} ${won ? "winstreak" : "loss streak"}`;
    return (
        <Stack
            direction="row"
            alignItems="center"
            gap={0.75}
            sx={{
                px: 1.25,
                py: 0.75,
                borderRadius: 0.75,
                bgcolor: alpha(color, 0.08),
                color,
                flexShrink: 0,
            }}
        >
            <Icon fontSize="small" sx={{ color }} />
            <Typography
                variant="body2"
                sx={{ color, fontWeight: 600, whiteSpace: "nowrap" }}
            >
                {label}
            </Typography>
        </Stack>
    );
};

const MomentumStrip: React.FC<{ segments: readonly GameSegment[] }> = ({
    segments,
}) => {
    const [focused, setFocused] = React.useState<number | null>(null);
    // This component keeps its place in the tree when the user navigates to
    // another session, so `focused` would otherwise carry over and point at a
    // different game in the new set. Reset it whenever the segments change.
    const identity = segments.map((seg) => seg.end.queriedAt.toISOString()).join(",");
    const [prevIdentity, setPrevIdentity] = React.useState(identity);
    if (identity !== prevIdentity) {
        setPrevIdentity(identity);
        setFocused(null);
    }
    const focusedSegment = focused === null ? undefined : segments[focused];
    // Number every segment by running game count so the tiles, the expanded
    // detail and the trajectory chart all agree on which game is which.
    const numbers = segmentGameNumbers(segments);
    return (
        <Panel>
            <Box sx={{ mb: 1.5 }}>
                <Stack
                    direction="row"
                    justifyContent="space-between"
                    alignItems="center"
                    gap={2}
                    sx={{ mb: 0.5 }}
                >
                    <Typography variant="subtitle1">Game-by-game</Typography>
                    <StreakIndicator segments={segments} />
                </Stack>
                <Typography variant="caption" color="textSecondary">
                    Click a tile to inspect. Dashed tiles are gaps where individual
                    games can&apos;t be attributed — either no game was played, or
                    several couldn&apos;t be split apart.
                </Typography>
            </Box>
            <Box
                sx={{
                    display: "grid",
                    // Tiles share the row when there's room (1fr each), but
                    // never shrink below 120px — past that the container
                    // scrolls horizontally so long sessions stay legible
                    // instead of squishing every tile.
                    // Guard against `repeat(0, …)` — invalid CSS — for a
                    // segment-less session; callers only render this with
                    // games, but keep the grid template valid regardless.
                    gridTemplateColumns: `repeat(${Math.max(1, segments.length).toString()}, minmax(120px, 1fr))`,
                    gap: 1,
                    overflowX: "auto",
                    pb: 1,
                }}
            >
                {segments.map((seg, i) => (
                    <GameTile
                        key={seg.end.queriedAt.toISOString()}
                        segment={seg}
                        numbering={numbers[i]}
                        active={focused === i}
                        onClick={() => {
                            setFocused((prev) => (prev === i ? null : i));
                        }}
                    />
                ))}
            </Box>
            {focusedSegment !== undefined && focused !== null && (
                <GameDetail segment={focusedSegment} numbering={numbers[focused]} />
            )}
        </Panel>
    );
};

interface TrajectoryChartProps {
    session: NonNullable<SessionAt["session"]>;
    segments: readonly GameSegment[];
}

const TrajectoryChart: React.FC<TrajectoryChartProps> = ({ session, segments }) => {
    const theme = useTheme();
    // NOTE: Assume the id format is CSS-selector-safe
    const gradientId = `fkdr-fill-${React.useId()}`;
    const points = fkdrTrajectory(session, segments);

    if (points.length < 2) {
        return (
            <Panel sx={{ height: "100%" }}>
                <Typography variant="subtitle1">FKDR trajectory</Typography>
                <Typography variant="caption" color="textSecondary">
                    Not enough games to draw a trajectory.
                </Typography>
            </Panel>
        );
    }

    // Recharts wants a mutable array.
    const data = [...points];
    const primary = theme.palette.primary.main;
    const lifetimeColor = theme.palette.text.secondary;

    return (
        <Panel sx={{ height: "100%" }}>
            <Stack
                direction="row"
                justifyContent="space-between"
                alignItems="baseline"
                sx={{ mb: 1.5 }}
                flexWrap="wrap"
                gap={1}
            >
                <Box>
                    <Typography variant="subtitle1">FKDR trajectory</Typography>
                    <Typography variant="caption" color="textSecondary">
                        Session FKDR after each game vs. all-time
                    </Typography>
                </Box>
                <Stack direction="row" gap={1.75}>
                    <Stack direction="row" alignItems="center" gap={0.75}>
                        <Box
                            sx={{
                                width: 18,
                                height: 2,
                                bgcolor: primary,
                                borderRadius: 1,
                            }}
                        />
                        <Typography variant="caption" color="textSecondary">
                            Session
                        </Typography>
                    </Stack>
                    <Stack direction="row" alignItems="center" gap={0.75}>
                        <Box
                            sx={{
                                width: 18,
                                borderTop: `2px dashed ${lifetimeColor}`,
                            }}
                        />
                        <Typography variant="caption" color="textSecondary">
                            Lifetime
                        </Typography>
                    </Stack>
                </Stack>
            </Stack>
            <Box sx={{ width: "100%", height: 240 }}>
                <ComposedChart
                    data={data}
                    responsive
                    width="100%"
                    height="100%"
                    style={{ minWidth: 100 }}
                    margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
                >
                    <defs>
                        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor={primary} stopOpacity={0.32} />
                            <stop offset="100%" stopColor={primary} stopOpacity={0} />
                        </linearGradient>
                    </defs>
                    <CartesianGrid
                        stroke={theme.palette.divider}
                        strokeDasharray="2 4"
                    />
                    <XAxis
                        dataKey="label"
                        stroke={theme.palette.divider}
                        tick={{ fill: theme.palette.text.secondary, fontSize: 12 }}
                    />
                    <YAxis
                        domain={[0, "auto"]}
                        stroke={theme.palette.divider}
                        tick={{ fill: theme.palette.text.secondary, fontSize: 12 }}
                        tickFormatter={(v: number) => v.toFixed(1)}
                        width={40}
                    />
                    {/* Lifetime first so the session line + dots render on top. */}
                    <Line
                        name="Lifetime"
                        type="monotone"
                        dataKey="lifetimeFkdr"
                        stroke={lifetimeColor}
                        strokeWidth={1.5}
                        strokeDasharray="4 4"
                        dot={false}
                        activeDot={false}
                        isAnimationActive={false}
                    />
                    <Area
                        name="Session"
                        type="monotone"
                        dataKey="sessionFkdr"
                        stroke={primary}
                        strokeWidth={2.5}
                        fill={`url(#${gradientId})`}
                        dot={{
                            r: 4,
                            fill: theme.palette.background.paper,
                            stroke: primary,
                            strokeWidth: 2,
                        }}
                        activeDot={{ r: 5 }}
                        isAnimationActive={false}
                    />
                    <ChartTooltip
                        labelFormatter={(label) =>
                            typeof label === "string" ? label : ""
                        }
                        formatter={(value) =>
                            typeof value === "number"
                                ? formatStatValue("fkdr", value)
                                : String(value)
                        }
                        contentStyle={{
                            backgroundColor: theme.palette.background.paper,
                            border: `1px solid ${theme.palette.divider}`,
                            borderRadius: 8,
                        }}
                        itemStyle={{ color: theme.palette.text.primary }}
                        labelStyle={{ color: theme.palette.text.secondary }}
                    />
                </ComposedChart>
            </Box>
        </Panel>
    );
};

interface SessionMetaCardProps {
    session: NonNullable<SessionAt["session"]>;
    agg: SessionAggregate;
}

const SessionMetaCard: React.FC<SessionMetaCardProps> = ({ session, agg }) => {
    const avgGameMs = agg.games > 0 ? agg.elapsedMs / agg.games : 0;
    const items: [string, string][] = [
        [
            "Started",
            session.start.queriedAt.toLocaleTimeString(undefined, {
                timeStyle: "short",
            }),
        ],
        [
            "Ended",
            session.end.queriedAt.toLocaleTimeString(undefined, {
                timeStyle: "short",
            }),
        ],
        ["Avg game", agg.games > 0 ? formatDuration(avgGameMs) : "—"],
        ["Finals", `${agg.fk.toString()} / ${agg.fd.toString()}`],
        ["Beds", `${agg.bb.toString()} / ${agg.bl.toString()}`],
        ["XP", `+${agg.xp.toLocaleString()}`],
    ];
    return (
        <Panel sx={{ height: "100%" }}>
            <Typography variant="subtitle1" sx={{ mb: 1.75 }}>
                Totals
            </Typography>
            <Box
                sx={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: 1.75,
                }}
            >
                {items.map(([label, value]) => (
                    <Box key={label}>
                        <Typography
                            variant="caption"
                            color="textSecondary"
                            sx={{ textTransform: "uppercase", letterSpacing: 0.6 }}
                        >
                            {label}
                        </Typography>
                        <Typography sx={{ fontFamily: "monospace", mt: 0.5 }}>
                            {value}
                        </Typography>
                    </Box>
                ))}
            </Box>
        </Panel>
    );
};

const ModeDetail: React.FC<{
    label: string;
    stats: ModeStats;
    color: string;
}> = ({ label, stats, color }) => {
    // Single-stat rows use the app's canonical short labels; the combined rows
    // (a "X / Y" pair of two stats) keep bespoke headers.
    const items: [string, string][] = [
        [getShortStatLabel("gamesPlayed", true), stats.games.toString()],
        ["Record", `${stats.wins.toString()}W · ${stats.losses.toString()}L`],
        [getShortStatLabel("winrate", true), formatStatValue("winrate", stats.winRate)],
        [getShortStatLabel("fkdr", true), formatStatValue("fkdr", stats.fkdr)],
        ["Finals", `${stats.fk.toString()} / ${stats.fd.toString()}`],
        ["Beds", `${stats.bb.toString()} / ${stats.bl.toString()}`],
        ["Kills", `${stats.k.toString()} / ${stats.d.toString()}`],
        [getShortStatLabel("kdr", true), formatStatValue("kdr", stats.kdr)],
    ];
    return (
        <Box sx={{ mt: 1.75, pt: 1.75, borderTop: 1, borderColor: "divider" }}>
            <Box
                sx={{
                    display: "grid",
                    gridTemplateColumns: "repeat(4, 1fr)",
                    gap: 1,
                    maxWidth: 720,
                    mx: "auto",
                }}
            >
                <Stack
                    direction="row"
                    alignItems="center"
                    gap={0.75}
                    sx={{ gridColumn: "1 / -1", mb: 0.5 }}
                >
                    <Box
                        sx={{ width: 8, height: 8, borderRadius: 0.25, bgcolor: color }}
                    />
                    <Typography
                        variant="caption"
                        color="textSecondary"
                        sx={{
                            textTransform: "uppercase",
                            letterSpacing: 0.6,
                            fontSize: 10,
                        }}
                    >
                        {label}
                    </Typography>
                </Stack>
                {items.map(([itemLabel, value]) => (
                    <Box key={itemLabel}>
                        <Typography
                            variant="caption"
                            color="textSecondary"
                            sx={{
                                textTransform: "uppercase",
                                letterSpacing: 0.6,
                                fontSize: 10,
                            }}
                        >
                            {itemLabel}
                        </Typography>
                        <Typography
                            sx={{ fontFamily: "monospace", fontSize: 14, mt: 0.5 }}
                        >
                            {value}
                        </Typography>
                    </Box>
                ))}
            </Box>
        </Box>
    );
};

const ModeBreakdown: React.FC<{
    session: NonNullable<SessionAt["session"]>;
}> = ({ session }) => {
    const theme = useTheme();
    const data = modeBreakdown(session);
    const [expanded, setExpanded] = React.useState<ModeBreakdownKey | null>(null);

    // The four original modes always show; the 4v4 tile and the "Other"
    // bucket (Dreams modes) only appear when games were played in them.
    const entries: {
        key: ModeBreakdownKey;
        label: string;
        color: string;
        stats: ModeStats;
    }[] = GAMEMODES.filter((mode) => mode !== "4v4" || data[mode].games > 0).map(
        (mode) => ({
            key: mode,
            label: getGamemodeLabel(mode, true),
            color: theme.palette.gamemode[mode],
            stats: data[mode],
        }),
    );
    if (data.other.games > 0) {
        entries.push({
            key: "other",
            label: "Other",
            color: theme.palette.textMuted,
            stats: data.other,
        });
    }
    const expandedEntry = entries.find((entry) => entry.key === expanded);

    return (
        <Panel>
            <Box sx={{ mb: 1.75 }}>
                <Typography variant="subtitle1">By gamemode</Typography>
                <Typography variant="caption" color="textSecondary">
                    Click a mode for the full breakdown
                </Typography>
            </Box>
            <Box
                sx={{
                    display: "grid",
                    gridTemplateColumns: { xs: "repeat(2, 1fr)", sm: "repeat(4, 1fr)" },
                    gap: 1.25,
                }}
            >
                {entries.map(({ key, label, color, stats }) => {
                    const empty = stats.games === 0;
                    const active = expanded === key;
                    return (
                        <Button
                            key={key}
                            disabled={empty}
                            onClick={() => {
                                setExpanded((prev) => (prev === key ? null : key));
                            }}
                            aria-expanded={active}
                            sx={{
                                p: 1.75,
                                borderRadius: 1.25,
                                bgcolor: active ? alpha(color, 0.13) : "action.hover",
                                border: 1,
                                borderColor: active ? color : "divider",
                                color: "text.primary",
                                textTransform: "none",
                                textAlign: "left",
                                flexDirection: "column",
                                alignItems: "stretch",
                                minWidth: 0,
                                opacity: empty ? 0.4 : 1,
                                "&:hover": { bgcolor: alpha(color, 0.07) },
                            }}
                        >
                            <Stack
                                direction="row"
                                alignItems="center"
                                gap={0.75}
                                sx={{ mb: 1.25 }}
                            >
                                <Box
                                    sx={{
                                        width: 8,
                                        height: 8,
                                        borderRadius: 0.25,
                                        bgcolor: color,
                                    }}
                                />
                                <Typography variant="body2" sx={{ fontWeight: 500 }}>
                                    {label}
                                </Typography>
                                {key === "other" && (
                                    <Tooltip title="Games played in modes that aren't broken out individually, such as a Dreams mode.">
                                        <Help
                                            sx={{
                                                fontSize: 14,
                                                color: "text.disabled",
                                                ml: "auto",
                                            }}
                                        />
                                    </Tooltip>
                                )}
                            </Stack>
                            <Typography sx={{ fontSize: 22, lineHeight: 1.1 }}>
                                {stats.games.toString()}
                            </Typography>
                            <Typography variant="caption" color="textSecondary">
                                {`games · ${stats.wins.toString()}W`}
                            </Typography>
                            <LinearProgress
                                variant="determinate"
                                value={stats.winRate * 100}
                                sx={{
                                    mt: 1.5,
                                    height: 4,
                                    borderRadius: 1,
                                    bgcolor: "divider",
                                    "& .MuiLinearProgress-bar": { bgcolor: color },
                                }}
                            />
                            <Stack
                                direction="row"
                                justifyContent="space-between"
                                sx={{ mt: 1 }}
                            >
                                <Typography variant="caption" color="textSecondary">
                                    FKDR
                                </Typography>
                                <Typography
                                    variant="caption"
                                    sx={{ fontFamily: "monospace" }}
                                >
                                    {formatStatValue("fkdr", stats.fkdr)}
                                </Typography>
                            </Stack>
                        </Button>
                    );
                })}
            </Box>
            {expandedEntry !== undefined && (
                <ModeDetail
                    label={expandedEntry.label}
                    stats={expandedEntry.stats}
                    color={expandedEntry.color}
                />
            )}
        </Panel>
    );
};

const MilestonesCard: React.FC<{ milestones: readonly Milestone[] }> = ({
    milestones,
}) => {
    const theme = useTheme();
    return (
        <Panel>
            <Typography variant="subtitle1">Milestones</Typography>
            <Typography variant="caption" color="textSecondary" sx={{ mb: 1.75 }}>
                At this session&apos;s pace
            </Typography>
            <Box
                sx={{
                    mt: 1.75,
                    display: "grid",
                    gridTemplateColumns: { xs: "1fr", sm: "repeat(3, 1fr)" },
                    gap: 1.25,
                }}
            >
                {milestones.map((m) => {
                    const Icon = MILESTONE_ICONS[m.key];
                    const color = milestoneColor(theme, m.key);
                    const reachable = m.target !== null && Number.isFinite(m.sessions);
                    // Stars and wins only ever climb (green, up); FKDR is
                    // session-dependent, so an underperforming session projects a
                    // lower target, surfaced via getTrendSentiment as a red
                    // down-trend — matching the regular session page.
                    const trend =
                        m.target === null
                            ? "flat"
                            : getTrendDirection(m.current, m.target);
                    const trendSentiment = getTrendSentiment(
                        MILESTONE_STAT[m.key],
                        trend,
                    );
                    return (
                        <Box
                            key={m.key}
                            sx={{
                                bgcolor: "action.hover",
                                border: 1,
                                borderColor: "divider",
                                borderRadius: 1.25,
                                p: 2,
                                display: "flex",
                                flexDirection: "column",
                                gap: 1.25,
                            }}
                        >
                            <Stack direction="row" alignItems="center" gap={1}>
                                <Box
                                    sx={{
                                        width: 28,
                                        height: 28,
                                        borderRadius: 0.875,
                                        bgcolor: alpha(color, 0.12),
                                        display: "flex",
                                        alignItems: "center",
                                        justifyContent: "center",
                                    }}
                                >
                                    <Icon sx={{ fontSize: 16, color }} />
                                </Box>
                                <Typography
                                    variant="caption"
                                    color="textSecondary"
                                    sx={{
                                        textTransform: "uppercase",
                                        letterSpacing: 0.6,
                                    }}
                                >
                                    {m.label}
                                </Typography>
                            </Stack>
                            <Stack
                                direction="row"
                                alignItems="baseline"
                                gap={1}
                                sx={{ fontFamily: "monospace" }}
                            >
                                <Typography sx={{ fontSize: 18 }}>
                                    {m.format(m.current)}
                                </Typography>
                                <TrendIcon
                                    direction={trend}
                                    sx={{
                                        fontSize: 16,
                                        color: SENTIMENT_COLOR[trendSentiment],
                                    }}
                                />
                                <Typography sx={{ fontSize: 18, color }}>
                                    {m.target === null ? "—" : m.format(m.target)}
                                </Typography>
                            </Stack>
                            {reachable ? (
                                <Box>
                                    <Stack
                                        direction="row"
                                        alignItems="baseline"
                                        gap={0.75}
                                    >
                                        <Typography
                                            sx={{ fontSize: 26, lineHeight: 1 }}
                                        >
                                            {m.sessions < 1
                                                ? "This session"
                                                : Math.ceil(m.sessions).toString()}
                                        </Typography>
                                        {m.sessions >= 1 && (
                                            <Typography
                                                variant="caption"
                                                color="textSecondary"
                                            >
                                                {`session${Math.ceil(m.sessions) === 1 ? "" : "s"} like this`}
                                            </Typography>
                                        )}
                                    </Stack>
                                    {m.sessions >= 1 && (
                                        <Stack
                                            direction="row"
                                            gap={0.5}
                                            alignItems="center"
                                            sx={{ mt: 0.75 }}
                                        >
                                            <Schedule
                                                sx={{
                                                    fontSize: 12,
                                                    color: "text.disabled",
                                                }}
                                            />
                                            <Typography
                                                variant="caption"
                                                color="textSecondary"
                                                sx={{ fontFamily: "monospace" }}
                                            >
                                                {`≈ ${formatDuration(m.playtimeMs)} of playtime`}
                                            </Typography>
                                        </Stack>
                                    )}
                                </Box>
                            ) : (
                                <Stack
                                    direction="row"
                                    alignItems="center"
                                    gap={0.75}
                                    color="text.disabled"
                                >
                                    <Block fontSize="small" />
                                    <Typography variant="caption">
                                        {m.blockedReason ?? "Not on pace to reach this"}
                                    </Typography>
                                </Stack>
                            )}
                            <Typography
                                variant="caption"
                                color="textSecondary"
                                sx={{ fontFamily: "monospace" }}
                            >
                                {m.deltaFormat()}
                            </Typography>
                        </Box>
                    );
                })}
            </Box>
        </Panel>
    );
};

interface HighlightItem {
    readonly id: string;
    readonly icon: SvgIconComponent;
    readonly color: string;
    readonly title: string;
    readonly value: string;
    readonly sub: string;
}

const HighlightsCard: React.FC<{
    agg: SessionAggregate;
    segments: readonly GameSegment[];
}> = ({ agg, segments }) => {
    const theme = useTheme();
    const best = bestGame(segments);
    const fastest = fastestWin(segments);
    const hours = agg.elapsedMs / MS_PER_HOUR;

    // Classify session FKDR against lifetime (±10% band; see fkdrVsLifetime).
    const vsLifetime: { icon: SvgIconComponent; color: string; title: string } = {
        beating: {
            icon: TrendingUp,
            color: theme.palette.success.main,
            title: "FKDR beating lifetime",
        },
        below: {
            icon: TrendingDown,
            color: theme.palette.error.main,
            title: "FKDR below lifetime",
        },
        on_par: {
            icon: TrendingFlat,
            color: theme.palette.text.secondary,
            title: "FKDR on par with lifetime",
        },
    }[fkdrVsLifetime(agg)];

    // Number games by running game count so these labels match the momentum
    // strip and the trajectory chart (e.g. the 2nd win after a gap is G2, not G3).
    const numbers = segmentGameNumbers(segments);
    const bestIndex = best === undefined ? -1 : segments.indexOf(best);
    const fastestIndex = fastest === undefined ? -1 : segments.indexOf(fastest);
    const bestLabel = bestIndex === -1 ? null : gameNumberLabel(numbers[bestIndex]);
    const fastestLabel =
        fastestIndex === -1 ? null : gameNumberLabel(numbers[fastestIndex]);

    const items: readonly HighlightItem[] = [
        {
            id: "signature",
            icon: WorkspacePremium,
            color: theme.palette.warning.main,
            title: "Best game",
            value:
                best === undefined || bestLabel === null
                    ? "—"
                    : `${bestLabel} · ${best.game.finalKills.toString()} finals`,
            sub:
                best === undefined
                    ? "No single-game segments"
                    : `${best.game.kills.toString()} kills · ${getGamemodeLabel(best.game.gamemode, true)}`,
        },
        {
            id: "fastest",
            icon: Bolt,
            color: theme.palette.success.main,
            title: "Fastest win",
            value:
                fastest === undefined
                    ? "—"
                    : `${Math.max(1, Math.round(segmentDurationMs(fastest) / MS_PER_MINUTE)).toString()}m`,
            sub:
                fastest === undefined || fastestLabel === null
                    ? "No wins yet"
                    : `${fastestLabel} · ${getGamemodeLabel(fastest.game.gamemode, true)}`,
        },
        {
            id: "vs-lifetime",
            icon: vsLifetime.icon,
            color: vsLifetime.color,
            title: vsLifetime.title,
            value: formatStatValue("fkdr", agg.fkdr),
            sub: `vs ${formatStatValue("fkdr", agg.lifetimeFkdr)} all-time`,
        },
        {
            id: "pace",
            icon: Speed,
            color: theme.palette.secondary.main,
            title: "Pace",
            value: hours > 0 ? `${(agg.fk / hours).toFixed(1)} fk/hr` : "—",
            sub: hours > 0 ? `${(agg.games / hours).toFixed(1)} games/hr` : "",
        },
    ];

    return (
        <Panel>
            <Typography variant="subtitle1" sx={{ mb: 1.75 }}>
                Highlights
            </Typography>
            <Box
                sx={{
                    display: "grid",
                    gridTemplateColumns: { xs: "repeat(2, 1fr)", sm: "repeat(4, 1fr)" },
                    gap: 1.25,
                }}
            >
                {items.map((h) => (
                    <Box
                        key={h.id}
                        sx={{
                            bgcolor: "action.hover",
                            border: 1,
                            borderColor: "divider",
                            borderRadius: 1.25,
                            p: 1.75,
                            display: "flex",
                            flexDirection: "column",
                            gap: 0.75,
                        }}
                    >
                        <Box
                            sx={{
                                width: 32,
                                height: 32,
                                borderRadius: 1,
                                bgcolor: alpha(h.color, 0.12),
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                mb: 0.5,
                            }}
                        >
                            <h.icon sx={{ fontSize: 18, color: h.color }} />
                        </Box>
                        <Typography
                            variant="caption"
                            color="textSecondary"
                            sx={{ textTransform: "uppercase", letterSpacing: 0.6 }}
                        >
                            {h.title}
                        </Typography>
                        <Typography
                            sx={{ fontSize: 18, fontWeight: 500, lineHeight: 1.1 }}
                        >
                            {h.value}
                        </Typography>
                        <Typography variant="caption" color="textSecondary">
                            {h.sub}
                        </Typography>
                    </Box>
                ))}
            </Box>
        </Panel>
    );
};

interface SessionDetailProps {
    data: SessionAt;
    uuid: string;
    username: string | undefined;
    onShare: () => void;
}

const SessionDetail: React.FC<SessionDetailProps> = ({
    data,
    uuid,
    username,
    onShare,
}) => {
    if (data.session === null) return null;
    const { session, games } = data;
    const agg = aggregate(session);
    const tags = computeTags(agg);
    const milestones = computeMilestones(session, agg);

    const displayName = username ?? "Player";

    return (
        <Stack spacing={2}>
            <PlayerBanner
                uuid={uuid}
                username={displayName}
                session={session}
                agg={agg}
                onShare={onShare}
            />
            {tags.length > 0 && <TagsRow tags={tags} />}
            <KPIRow agg={agg} />
            {games.length > 0 && <MomentumStrip segments={games} />}
            <Stack
                direction={{ xs: "column", md: "row" }}
                gap={1.5}
                alignItems="stretch"
            >
                <Box sx={{ flex: 2, minWidth: 0 }}>
                    <TrajectoryChart session={session} segments={games} />
                </Box>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                    <SessionMetaCard session={session} agg={agg} />
                </Box>
            </Stack>
            <ModeBreakdown session={session} />
            <MilestonesCard milestones={milestones} />
            <HighlightsCard agg={agg} segments={games} />
        </Stack>
    );
};

function RouteComponent() {
    const { uuid: rawUUID } = Route.useParams();
    const { date } = Route.useSearch();
    const navigate = Route.useNavigate();
    const queryClient = useQueryClient();

    const uuid = normalizeUUID(rawUUID);

    const { data, isFetching, isError } = useQuery({
        ...getSessionAtQueryOptions({
            uuid: uuid ?? "",
            time: date,
        }),
        enabled: uuid !== null,
    });

    const uuidToUsername = useUUIDToUsername(uuid !== null ? [uuid] : []);
    const username = uuid !== null ? uuidToUsername[uuid] : undefined;

    const [snackbarOpen, setSnackbarOpen] = React.useState(false);

    // Normalize the URL date to the session's actual start time so the
    // URL is canonical and shareable. Pre-seed the cache for the
    // canonical query key to avoid a duplicate fetch after navigate.
    const sessionStart = data?.session?.start.queriedAt;
    React.useEffect(() => {
        if (sessionStart === undefined) return;
        if (uuid === null) return;
        if (sessionStart.getTime() === date.getTime()) return;
        const run = async () => {
            try {
                queryClient.setQueryData(
                    getSessionAtQueryOptions({ uuid, time: sessionStart }).queryKey,
                    data,
                );
                await navigate({
                    replace: true,
                    search: (old) => ({ ...old, date: sessionStart }),
                });
            } catch (error: unknown) {
                captureException(error, {
                    tags: { param: "date" },
                    extra: { message: "Failed to normalize session detail URL" },
                });
            }
        };
        void run();
    }, [sessionStart, date, navigate, queryClient, uuid, data]);

    if (uuid === null) {
        return <Navigate to="/session" replace />;
    }

    if (uuid !== rawUUID) {
        return (
            <Navigate
                from="/session/$uuid/detail"
                to="/session/$uuid/detail"
                replace
                params={{ uuid }}
                search={(old) => ({ ...old, date })}
            />
        );
    }

    const handleShare = () => {
        const url = globalThis.location.href;
        const run = async () => {
            try {
                await navigator.clipboard.writeText(url);
                setSnackbarOpen(true);
            } catch (error: unknown) {
                captureException(error, {
                    extra: { message: "Failed to copy share link" },
                });
            }
        };
        void run();
    };

    const displayName = username ?? "Player";

    return (
        <Stack spacing={2}>
            <meta
                name="description"
                content={`${displayName}'s Bedwars session detail.`}
            />
            {isFetching && data === undefined && (
                <Skeleton variant="rounded" height={140} />
            )}
            {isError && !isFetching && (
                <Alert severity="error">Failed to load session.</Alert>
            )}
            {!isFetching && data !== undefined && data.session === null && (
                <NoSession username={displayName} />
            )}
            {data !== undefined && data.session !== null && (
                <SessionDetail
                    data={data}
                    uuid={uuid}
                    username={username}
                    onShare={handleShare}
                />
            )}
            <Snackbar
                open={snackbarOpen}
                autoHideDuration={2500}
                onClose={() => {
                    setSnackbarOpen(false);
                }}
                anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
            >
                <Alert
                    severity="success"
                    variant="filled"
                    icon={<ContentCopy fontSize="small" />}
                    sx={{ width: "100%" }}
                >
                    Link copied!
                </Alert>
            </Snackbar>
        </Stack>
    );
}
