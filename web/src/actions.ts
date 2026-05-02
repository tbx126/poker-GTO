/**
 * Action color regime per the design guide:
 *   蓝/紫 cold  → fold
 *   绿  neutral → check / call
 *   红渐变 warm → bet from small probe (light red) to all-in (deep crimson)
 *
 * Sizings are pot fractions; "allin" is its own bucket.
 */

export type ActionKey =
  | "fold"
  | "check_call"
  | "bet_25"
  | "bet_50"
  | "bet_75"
  | "bet_100"
  | "bet_150"
  | "allin";

export interface ActionMeta {
  key: ActionKey;
  label: string;
  /** Hex color used for the strip in the heatmap. */
  color: string;
}

export const ACTIONS: ActionMeta[] = [
  { key: "fold",       label: "Fold",     color: "#3a3f9b" },
  { key: "check_call", label: "Check/Call", color: "#3da55a" },
  { key: "bet_25",     label: "Bet 25%",  color: "#f4b884" },
  { key: "bet_50",     label: "Bet 50%",  color: "#ec8a5a" },
  { key: "bet_75",     label: "Bet 75%",  color: "#e0623f" },
  { key: "bet_100",    label: "Bet pot",  color: "#c43c2c" },
  { key: "bet_150",    label: "Bet 150%", color: "#992020" },
  { key: "allin",      label: "All-in",   color: "#5c0e0e" },
];

export const ACTION_INDEX: Record<ActionKey, number> = ACTIONS.reduce(
  (acc, a, i) => ({ ...acc, [a.key]: i }),
  {} as Record<ActionKey, number>,
);

/** Strategy at one hand: probability mass per action; should sum to ~1. */
export type HandStrategy = Partial<Record<ActionKey, number>>;
