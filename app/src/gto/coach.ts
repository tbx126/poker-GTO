import { GameState, Move, legalMoves } from "../engine/game";
import { approxStrategy } from "./approx";
import { IndexedTable, lookupPreflop } from "./preflop";
import type { ActionAdvice, Strategy } from "./types";

/**
 * 翻后两人底池求解器。桌面应用里由 Tauri 后端（crates/solver-api）实现，
 * 浏览器里没有，翻后一律用规则近似。
 */
export interface PostflopSolver {
  /** 当前局面能否求解：翻牌开始就是两人底池。 */
  supports(s: GameState): Promise<boolean>;
  /** 新的一条街发出来时调用，立即在后台开始求解。 */
  prepare(s: GameState): void;
  /** 等这条街求解完，返回 seat 在当前节点的策略。 */
  solve(s: GameState, seat: number): Promise<Strategy>;
  /** 一手牌结束时释放后台求解。 */
  cancel(handId: string): void;
}

let solver: PostflopSolver | null = null;
export function setPostflopSolver(s: PostflopSolver | null) {
  solver = s;
}
export const postflopSolver = () => solver;

export async function strategyFor(s: GameState, seat: number, table: IndexedTable | null): Promise<Strategy> {
  if (s.street === 0 && table) {
    const hit = lookupPreflop(table, s, seat);
    if (hit) return hit;
  }
  if (s.street > 0 && solver) {
    try {
      if (await solver.supports(s)) {
        const solved = await solver.solve(s, seat);
        if (solved.actions.length) return solved;
      }
    } catch (e) {
      // 求解失败（范围表缺失、局面不在树里等）时退回近似，不打断对局。
      console.warn("求解器不可用，改用近似策略：", e);
    }
  }
  return approxStrategy(s, seat);
}

/** 求解器返回的一个动作，字段和 crates/solver-api 的 ActionAdvice 一致。 */
export interface SolverAction {
  kind: Move["kind"];
  to: number;
  freq: number;
  ev: number;
}

/**
 * 把求解器的动作对应到规则引擎的合法动作：弃牌、过牌、跟注按类型，
 * 下注、加注、全下按金额最接近的一个，避免两边金额取整不同时对不上。
 * 对应不上的合法动作不列出。
 */
export function mapSolverActions(s: GameState, actions: SolverAction[], exploitability?: number): Strategy {
  const legal = legalMoves(s);
  const aggressive = legal.filter((m) => m.kind === "bet" || m.kind === "raise" || m.kind === "allin");
  const merged = new Map<Move, ActionAdvice>();
  for (const a of actions) {
    let move: Move | undefined;
    if (a.kind === "fold" || a.kind === "check" || a.kind === "call") move = legal.find((m) => m.kind === a.kind);
    else
      move = aggressive.reduce<Move | undefined>(
        (best, m) => (!best || Math.abs(m.to - a.to) < Math.abs(best.to - a.to) ? m : best),
        undefined,
      );
    if (!move) continue;
    const prev = merged.get(move);
    if (prev) {
      prev.ev = (prev.ev! * prev.freq + a.ev * a.freq) / Math.max(prev.freq + a.freq, 1e-9);
      prev.freq += a.freq;
    } else merged.set(move, { move, freq: a.freq, ev: a.ev });
  }
  const list = legal.filter((m) => merged.has(m)).map((m) => merged.get(m)!);
  const total = list.reduce((x, a) => x + a.freq, 0) || 1;
  for (const a of list) {
    a.freq /= total;
    a.ev = Math.round(a.ev! * 100) / 100;
  }
  return { source: "solver", actions: list, exploitability };
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
  // 选的动作不在策略里（例如求解器的树没有这个尺寸）时没法算 EV，按频率 0 处理。
  const hasEv = mine !== undefined && strategy.actions.every((a) => a.ev !== undefined);
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
