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


// ----- Preflop Strategy Matrix (169 hands) -----

export interface HandStrategy {
  hand: string;
  actions: string[];
  probs: number[];
  action_kinds: string[];
}

export interface PreflopStrategyResponse {
  scenario_description: string;
  hero_position: string;
  scenario_type: string;
  strategies: Record<string, HandStrategy>;
  vpip: number;
  raise_freq: number;
  call_freq: number;
}

export interface PreflopScenarioRequest {
  table_size: number;
  effective_stack: number;
  hero_position: string;
  scenario_type: "open" | "face_open" | "face_3bet" | "face_4bet";
  raiser_position?: string;
  raise_size?: number;
  three_bettor?: string;
  three_bet_size?: number;
}

export async function getPreflopStrategyMatrix(
  req: PreflopScenarioRequest
): Promise<PreflopStrategyResponse> {
  const r = await fetch(`${API_BASE}/strategy/preflop_matrix`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`/strategy/preflop_matrix ${r.status}: ${text}`);
  }
  return (await r.json()) as PreflopStrategyResponse;
}
