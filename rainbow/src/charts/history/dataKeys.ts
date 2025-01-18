import {
    type GamemodeKey,
    type GamemodeStatKey,
    type OverallStatKey,
    type StatKey,
    type VariantKey,
} from "#stats/keys.ts";

type UUID = string;

interface DataKeyInput {
    uuid: UUID;
    variant: VariantKey;
    gamemode: GamemodeKey;
    stat: StatKey;
}

export type DataKey =
    | `history-${UUID}-${VariantKey}-${OverallStatKey}`
    | `history-${UUID}-${VariantKey}-${GamemodeKey}-${GamemodeStatKey}`;

export const makeDataKey = ({
    uuid,
    variant,
    gamemode,
    stat,
}: DataKeyInput): DataKey => {
    if (stat === "experience" || stat === "stars") {
        return `history-${uuid}-${variant}-${stat}`;
    }
    return `history-${uuid}-${variant}-${gamemode}-${stat}`;
};
