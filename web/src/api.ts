/** Typed wrapper over the FastAPI solver service. */

export type GameName = "kuhn" | "leduc";

export interface TrajectoryPoint {
  iter: number;
  exploitability: number;
}

export interface StrategyEntry {
  infoset: string;
  actions: string[];
  probs: number[];
}

export interface SolveResponse {
  game: GameName;
  iters: number;
  final_exploitability: number;
  trajectory: TrajectoryPoint[];
  strategies: StrategyEntry[];
  elapsed_ms: number;
}

const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8090";

export async function solve(game: GameName, iters: number, chunks: number): Promise<SolveResponse> {
  const r = await fetch(`${API_BASE}/solve/${game}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ iters, chunks }),
  });
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`/solve/${game} ${r.status}: ${text}`);
  }
  return (await r.json()) as SolveResponse;
}

export async function ping(): Promise<boolean> {
  try {
    const r = await fetch(`${API_BASE}/healthz`);
    return r.ok;
  } catch {
    return false;
  }
}

// ----- preflop -----

export type PanelSide = "SB" | "BB";

export interface PreflopPanel {
  side: PanelSide;
  title: string;
  subtitle: string;
  history: string[];
  actions: string[];
  action_kinds: string[];
  by_class: Record<string, number[]>;
}

export interface PreflopResponse {
  iters: number;
  final_exploitability: number;
  elapsed_ms: number;
  panels: PreflopPanel[];
}

export interface PreflopLock {
  history: string[];
  hand: string;
  probs: number[];
}

export interface TreeConfig {
  stack: number;
  sb_blind: number;
  bb_blind: number;
  open_to: number;
  threebet_to: number;
  fourbet_to: number | null; // null => all-in (= stack)
}

export const DEFAULT_TREE: TreeConfig = {
  stack: 100,
  sb_blind: 0.5,
  bb_blind: 1,
  open_to: 2.5,
  threebet_to: 9,
  fourbet_to: null,
};

export async function solvePreflop(
  iters: number,
  locks: PreflopLock[] = [],
  tree: TreeConfig = DEFAULT_TREE,
): Promise<PreflopResponse> {
  const r = await fetch(`${API_BASE}/solve/preflop`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ iters, locks, tree }),
  });
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`/solve/preflop ${r.status}: ${text}`);
  }
  return (await r.json()) as PreflopResponse;
}
