/**
 * Mock strategies for the side-by-side panels.
 * Two scenarios: BTN vs BB, 100bb. Generated heuristically — they are
 * plausible, not solver-true. Replaced by real /solve responses in M2.
 */

import type { ActionKey, HandStrategy } from "./actions";
import { RANK_LABELS, handLabel } from "./hands";

export interface PanelMeta {
  history: string[];     // e.g., [] for SB first action, ["open"] for BB defense
  actions: string[];     // solver-side action labels
  action_kinds: string[];// frontend color-bucket alignment
}

export interface ScenarioStrategy {
  /** infoset description shown above each panel */
  title: string;
  subtitle: string;
  ev?: number;           // chips per hand for this side (optional in live mode)
  equity?: number;       // 0..1 raw equity (optional in live mode)
  vpip?: number;         // share of hands non-folded — meaningful for live solver output
  meta?: PanelMeta;      // present only in live mode; gates lock UI
  strategy: Record<string, HandStrategy>;
}

const rankIndex = (r: string) => RANK_LABELS.indexOf(r as (typeof RANK_LABELS)[number]);

function pairRank(label: string): number {
  return rankIndex(label[0]);
}

function suitedRanks(label: string): { hi: number; lo: number } {
  return { hi: rankIndex(label[0]), lo: rankIndex(label[1]) };
}

/** OOP strategy: BB defense vs BTN raise. Mostly defensive (call / fold). */
function buildOOPDefense(): Record<string, HandStrategy> {
  const out: Record<string, HandStrategy> = {};
  for (let r = 0; r < 13; r++) {
    for (let c = 0; c < 13; c++) {
      const label = handLabel(r, c);
      const strat: HandStrategy = {};
      if (r === c) {
        const pr = pairRank(label);
        if (pr <= 3) {
          // AA, KK, QQ, JJ → 3-bet heavy
          strat.bet_100 = 0.7;
          strat.bet_150 = 0.2;
          strat.check_call = 0.1;
        } else if (pr <= 6) {
          // TT, 99, 88, 77 → mostly call
          strat.check_call = 0.85;
          strat.bet_100 = 0.15;
        } else {
          strat.check_call = 0.65;
          strat.fold = 0.35;
        }
      } else {
        const { hi, lo } = suitedRanks(label);
        const isSuited = label.endsWith("s");
        const strength = (12 - hi) * 1.4 + (12 - lo) + (isSuited ? 3 : 0);

        if (strength > 18) {
          strat.bet_100 = 0.5;
          strat.check_call = 0.4;
          strat.bet_150 = 0.1;
        } else if (strength > 13) {
          strat.check_call = 0.7;
          strat.fold = 0.2;
          strat.bet_100 = 0.1;
        } else if (strength > 9) {
          strat.check_call = 0.35;
          strat.fold = 0.65;
        } else {
          strat.fold = 1.0;
        }
      }
      out[label] = strat;
    }
  }
  return out;
}

/** IP strategy: BTN open. Wide raising, very few calls (since SB/BB acts after). */
function buildIPOpen(): Record<string, HandStrategy> {
  const out: Record<string, HandStrategy> = {};
  for (let r = 0; r < 13; r++) {
    for (let c = 0; c < 13; c++) {
      const label = handLabel(r, c);
      const strat: HandStrategy = {};
      if (r === c) {
        const pr = pairRank(label);
        if (pr <= 1) {
          strat.bet_75 = 0.4;
          strat.bet_100 = 0.6;
        } else if (pr <= 5) {
          strat.bet_50 = 0.7;
          strat.bet_75 = 0.3;
        } else {
          strat.bet_25 = 0.4;
          strat.bet_50 = 0.6;
        }
      } else {
        const { hi, lo } = suitedRanks(label);
        const isSuited = label.endsWith("s");
        const strength = (12 - hi) * 1.5 + (12 - lo) + (isSuited ? 4 : 0);

        if (strength > 18) {
          strat.bet_75 = 0.3;
          strat.bet_100 = 0.7;
        } else if (strength > 13) {
          strat.bet_50 = 0.5;
          strat.bet_75 = 0.5;
        } else if (strength > 9) {
          strat.bet_25 = 0.6;
          strat.fold = 0.4;
        } else if (strength > 6) {
          strat.bet_25 = 0.2;
          strat.fold = 0.8;
        } else {
          strat.fold = 1.0;
        }
      }
      out[label] = strat;
    }
  }
  return out;
}

export const SCENARIO_BTN_VS_BB: { oop: ScenarioStrategy; ip: ScenarioStrategy } = {
  oop: {
    title: "OOP — BB",
    subtitle: "facing 2.5x BTN open, 100bb",
    ev: -0.42,
    equity: 0.469,
    strategy: buildOOPDefense(),
  },
  ip: {
    title: "IP — BTN",
    subtitle: "open vs SB/BB, 100bb",
    ev: 1.83,
    equity: 0.531,
    strategy: buildIPOpen(),
  },
};

export const ACTION_ORDER_BARS: ActionKey[] = [
  "fold",
  "check_call",
  "bet_25",
  "bet_50",
  "bet_75",
  "bet_100",
  "bet_150",
  "allin",
];
