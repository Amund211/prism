import type { History } from "#queries/history.ts";
import type { PlayerDataPIT } from "#queries/playerdata.ts";
import type { Session, Sessions } from "#queries/sessions.ts";

const statsConsecutive = (a: PlayerDataPIT, b: PlayerDataPIT): boolean => {
    return Math.abs(a.overall.gamesPlayed - b.overall.gamesPlayed) <= 1;
};

const differentStats = (a: PlayerDataPIT, b: PlayerDataPIT): boolean => {
    return (
        a.overall.gamesPlayed !== b.overall.gamesPlayed ||
        a.experience !== b.experience
    );
};

// Add sessions where there are stat-gaps between the end of the previous session
// and the start of the next session
export const addExtrapolatedSessions = (
    sessions: Sessions,
    history: History | undefined,
): Sessions => {
    if (!history || history.length !== 2) {
        // If there is no history, we cannot extrapolate at the start or end
        // We could still extrapolate between sessions, but don't do that for now
        return sessions;
    }

    const [historyStart, historyEnd] = history;

    if (sessions.length === 0) {
        if (!differentStats(historyStart, historyEnd)) {
            return [];
        }

        return [
            {
                start: historyStart,
                end: historyEnd,
                extrapolated: true,
                consecutive: statsConsecutive(historyStart, historyEnd),
            },
        ];
    }

    const firstSessionStart = sessions[0].start;
    const lastSessionEnd = sessions[sessions.length - 1].end;

    const startNonFlashlightSession = differentStats(
        historyStart,
        firstSessionStart,
    )
        ? [
              {
                  start: historyStart,
                  end: firstSessionStart,
                  extrapolated: true,
                  consecutive: statsConsecutive(
                      historyStart,
                      firstSessionStart,
                  ),
              },
          ]
        : [];

    const endNonFlashlightSession = differentStats(lastSessionEnd, historyEnd)
        ? [
              {
                  start: lastSessionEnd,
                  end: historyEnd,
                  extrapolated: true,
                  consecutive: statsConsecutive(lastSessionEnd, historyEnd),
              },
          ]
        : [];

    const sessionsWithExtrapolated: Session[] = [];
    for (let i = 0; i < sessions.length - 1; i++) {
        sessionsWithExtrapolated.push(sessions[i]);
        const previousSession = sessions[i];
        const nextSession = sessions[i + 1];

        if (differentStats(previousSession.end, nextSession.start)) {
            sessionsWithExtrapolated.push({
                start: previousSession.end,
                end: nextSession.start,
                extrapolated: true,
                consecutive: statsConsecutive(
                    previousSession.end,
                    nextSession.start,
                ),
            });
        }
    }

    if (sessions.length > 0) {
        sessionsWithExtrapolated.push(sessions[sessions.length - 1]);
    }

    return [
        ...startNonFlashlightSession,
        ...sessionsWithExtrapolated,
        ...endNonFlashlightSession,
    ];
};
