import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { cardName } from "../engine/cards";
import { GameState, preflopHistory } from "../engine/game";
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
    const r = await invoke<{ actions: SolverAction[]; exploitability: number }>("solver_strategy", {
      state: handState(s),
      seat,
    });
    return mapSolverActions(s, r.actions, r.exploitability);
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
