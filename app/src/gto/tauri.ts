import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { cardName } from "../engine/cards";
import { GameState, legalMoves, preflopHistory } from "../engine/game";
import { PostflopSolver, SolverAction, mapSolverActions } from "./coach";

/** 是否运行在 Tauri 桌面应用里（浏览器里没有后端求解器）。 */
export const inDesktop = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

/** crates/solver-api 的 Progress。 */
export interface SolverProgress {
  handId: string;
  street: number;
  iteration: number;
  /** 可剥削度占这条街起始底池的比例。 */
  exploitability: number;
  /** 0 到 1。 */
  fraction: number;
  done: boolean;
  /** 到达目标精度（false 表示到了时间或轮数上限）。 */
  converged: boolean;
}

/** 把规则引擎的状态转换成 crates/solver-api 的 HandState。 */
export function handState(s: GameState) {
  return {
    handId: s.id,
    players: s.config.players,
    preflop: preflopHistory(s),
    board: s.board.map(cardName),
    postflop: s.events
      .filter((e) => e.street > 0)
      .map((e) => ({ street: e.street, seat: e.seat, kind: e.move.kind, to: e.move.to })),
    cards: s.seats.map((x) => x.cards.map(cardName)),
  };
}

export const tauriSolver: PostflopSolver = {
  supports: (s) => invoke<boolean>("solver_supports", { state: handState(s) }),
  prepare(s) {
    invoke("solver_prepare", { state: handState(s) }).catch((e) => console.warn("无法开始求解：", e));
  },
  async solve(s, seat) {
    const r = await invoke<{ actions: SolverAction[]; exploitability: number; converged: boolean }>("solver_strategy", {
      state: handState(s),
      seat,
    });
    return mapSolverActions(s, r.actions, r.exploitability, r.converged);
  },
  async approx(s, seat) {
    const legal = legalMoves(s);
    const r = await invoke<{ actions: { freq: number; ev: number }[]; equity: number }>("solver_approx", {
      state: handState(s),
      seat,
      legal: legal.map((m) => ({ kind: m.kind, to: m.to })),
    });
    // 后端按传入的合法动作逐一返回，顺序相同。
    if (r.actions.length !== legal.length) throw new Error("近似策略的动作数和合法动作对不上");
    return {
      source: "approx",
      actions: legal.map((move, i) => ({ move, freq: r.actions[i].freq, ev: Math.round(r.actions[i].ev * 100) / 100 })),
      equity: r.equity,
      equityVs: "ranges",
    };
  },
  cancel(handId) {
    invoke("solver_cancel", { handId }).catch(() => {});
  },
};

export function onSolverProgress(cb: (p: SolverProgress) => void): () => void {
  let stop: (() => void) | null = null;
  let stopped = false;
  listen<SolverProgress>("solver-progress", (e) => cb(e.payload)).then((un) => {
    if (stopped) un();
    else stop = un;
  });
  return () => {
    stopped = true;
    stop?.();
  };
}
