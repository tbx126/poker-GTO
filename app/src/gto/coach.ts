import { GameState, Move } from "../engine/game";
import { approxStrategy } from "./approx";
import { IndexedTable, lookupPreflop } from "./preflop";
import type { Strategy } from "./types";

/**
 * 翻后两人底池求解器的接口。Tauri 后端接入 crates/postflop 后实现它，
 * 没有注册时翻后一律用规则近似。
 */
export interface PostflopSolver {
  /** 当前局面能否求解（例如只支持两人底池）。 */
  supports(s: GameState): boolean;
  solve(s: GameState, seat: number, onProgress?: (fraction: number) => void): Promise<Strategy>;
}

let solver: PostflopSolver | null = null;
export function setPostflopSolver(s: PostflopSolver | null) {
  solver = s;
}

export async function strategyFor(
  s: GameState,
  seat: number,
  table: IndexedTable | null,
  onProgress?: (fraction: number) => void,
): Promise<Strategy> {
  if (s.street === 0 && table) {
    const hit = lookupPreflop(table, s, seat);
    if (hit) return hit;
  }
  if (s.street > 0 && solver?.supports(s)) return solver.solve(s, seat, onProgress);
  return approxStrategy(s, seat);
}

/** 按策略频率随机选一个动作，GTO 对手用它出牌。 */
export function sample(strategy: Strategy, random: () => number = Math.random): Move {
  let r = random();
  for (const a of strategy.actions) {
    r -= a.freq;
    if (r <= 0) return a.move;
  }
  return strategy.actions.reduce((x, y) => (y.freq > x.freq ? y : x)).move;
}

export type Grade = "best" | "good" | "inaccuracy" | "mistake" | "blunder";

export const GRADE_LABELS: Record<Grade, string> = {
  best: "最佳",
  good: "可行",
  inaccuracy: "欠佳",
  mistake: "失误",
  blunder: "大错",
};

export interface Feedback {
  street: number;
  chosen: Move;
  freq: number;
  best: Move;
  bestFreq: number;
  /** 比最好的动作少赚的 bb；只有策略带 EV 时才有。 */
  evLoss?: number;
  grade: Grade;
  strategy: Strategy;
  pot: number;
}

const sameMove = (a: Move, b: Move) => a.kind === b.kind && a.to === b.to;

export function judge(s: GameState, strategy: Strategy, chosen: Move, potNow: number): Feedback {
  const mine = strategy.actions.find((a) => sameMove(a.move, chosen));
  const top = strategy.actions.reduce((x, y) => (y.freq > x.freq ? y : x));
  const freq = mine?.freq ?? 0;
  let evLoss: number | undefined;
  let grade: Grade;
  const hasEv = strategy.actions.every((a) => a.ev !== undefined);
  if (hasEv) {
    const bestEv = Math.max(...strategy.actions.map((a) => a.ev!));
    evLoss = Math.max(0, Math.round((bestEv - (mine?.ev ?? 0)) * 100) / 100);
    const rel = evLoss / Math.max(potNow, 1);
    grade =
      mine === top || rel < 0.01
        ? "best"
        : rel < 0.04
          ? "good"
          : rel < 0.1
            ? "inaccuracy"
            : rel < 0.25
              ? "mistake"
              : "blunder";
  } else {
    grade =
      mine === top || freq >= 0.45
        ? "best"
        : freq >= 0.2
          ? "good"
          : freq >= 0.06
            ? "inaccuracy"
            : freq >= 0.01
              ? "mistake"
              : "blunder";
  }
  return {
    street: s.street,
    chosen,
    freq,
    best: top.move,
    bestFreq: top.freq,
    evLoss,
    grade,
    strategy,
    pot: potNow,
  };
}

/** 复盘排序用的“严重程度”：有 EV 时按损失的 bb，没有时按频率差折算。 */
export function severity(f: Feedback): number {
  if (f.evLoss !== undefined) return f.evLoss;
  return (f.bestFreq - f.freq) * f.pot * 0.5;
}
