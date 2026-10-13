import type { Move } from "../engine/game";

export interface ActionAdvice {
  move: Move;
  /** GTO 频率，0 到 1。 */
  freq: number;
  /** 这个动作相对“现在弃牌”的期望收益（bb）。翻前范围表没有 EV 时为 undefined。 */
  ev?: number;
}

/**
 * 某个座位在当前局面下的策略。
 * - table：翻前范围表（离线求解）。
 * - solver：翻后求解器（接入 Tauri 后端后提供）。
 * - approx：规则近似（多人底池，或求解器暂时不可用时）。
 */
export interface Strategy {
  source: "table" | "solver" | "approx";
  actions: ActionAdvice[];
  /** 对随机手牌的胜率，近似策略会给出。 */
  equity?: number;
}

export const SOURCE_LABELS: Record<Strategy["source"], string> = {
  table: "翻前范围表",
  solver: "求解器",
  approx: "近似",
};
