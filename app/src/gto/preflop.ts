import { handClass } from "../engine/cards";
import { GameState, legalMoves, preflopHistory } from "../engine/game";
import type { Strategy } from "./types";

/** `crates/preflop` 的 export_spots_json 导出的范围表格式。 */
export interface RangeTable {
  players: number;
  stack: number;
  iterations: number;
  max_gain_per_100: number;
  positions: string[];
  hands: string[];
  spots: Spot[];
}

export interface Spot {
  actor: string;
  history: string[];
  reach: number;
  actions: string[];
  /** 每手牌：[到达权重, 各动作频率...]，顺序和 RangeTable.hands 一致。 */
  hands: number[][];
  /** 每手牌每个动作的 EV（bb，整手牌的净输赢），和 hands 平行；旧版导出没有。 */
  ev?: number[][];
}

export interface IndexedTable {
  table: RangeTable;
  custom: boolean;
  byHistory: Map<string, Spot>;
  handIndex: Map<string, number>;
}

const CUSTOM_KEY = (n: number) => `custom-range-${n}`;
const cache = new Map<number, Promise<IndexedTable>>();

export function index(table: RangeTable, custom = false): IndexedTable {
  return {
    table,
    custom,
    byHistory: new Map(table.spots.map((s) => [s.history.join("|"), s])),
    handIndex: new Map(table.hands.map((h, i) => [h, i])),
  };
}

export function validateTable(value: unknown, players: number): RangeTable {
  const t = value as RangeTable;
  if (!t || typeof t !== "object" || !Array.isArray(t.spots) || !Array.isArray(t.hands))
    throw new Error("文件格式不对：需要求解器导出的范围表 JSON");
  if (t.players !== players) throw new Error(`这是 ${t.players} 人桌的范围表，当前选的是 ${players} 人`);
  if (t.hands.length !== 169) throw new Error("范围表应包含 169 种起手牌");
  for (const s of t.spots) {
    if (!Array.isArray(s.history) || !Array.isArray(s.actions) || s.hands.length !== 169 || (s.ev && s.ev.length !== 169))
      throw new Error(`局面 ${s.actor ?? "?"} 的数据不完整`);
  }
  return t;
}

function readCustom(players: number): RangeTable | null {
  try {
    const raw = localStorage.getItem(CUSTOM_KEY(players));
    return raw ? validateTable(JSON.parse(raw), players) : null;
  } catch {
    return null;
  }
}

export function saveCustom(players: number, table: RangeTable | null) {
  try {
    if (table) localStorage.setItem(CUSTOM_KEY(players), JSON.stringify(table));
    else localStorage.removeItem(CUSTOM_KEY(players));
  } catch {
    // 浏览器不允许存储时，自定义范围只在本次打开期间生效。
  }
  if (table) cache.set(players, Promise.resolve(index(table, true)));
  else cache.delete(players);
}

/** 读取某个人数的范围表；导入过自定义范围时优先使用自定义的。 */
export function loadTable(players: number): Promise<IndexedTable> {
  let p = cache.get(players);
  if (!p) {
    const custom = readCustom(players);
    p = custom
      ? Promise.resolve(index(custom, true))
      : fetch(`./ranges/${players}max.json`).then(async (res) => {
          if (!res.ok) throw new Error(`读取 ${players} 人范围表失败`);
          return index((await res.json()) as RangeTable);
        });
    p.catch(() => cache.delete(players));
    cache.set(players, p);
  }
  return p;
}

/** 在范围表里查当前行动者这手牌的策略；局面不在表里（例如 5bet 之后）时返回 null。 */
export function lookupPreflop(t: IndexedTable, s: GameState, seat: number): Strategy | null {
  if (s.street !== 0) return null;
  const spot = t.byHistory.get(preflopHistory(s).join("|"));
  if (!spot) return null;
  const [a, b] = s.seats[seat].cards;
  const h = t.handIndex.get(handClass(a, b));
  if (h === undefined) return null;
  const row = spot.hands[h];
  const moves = legalMoves(s);
  const actions = moves.map((move) => {
    const k = spot.actions.indexOf(move.label);
    return { move, freq: k >= 0 ? row[k + 1] : 0, ev: k >= 0 ? spot.ev?.[h][k] : undefined };
  });
  const total = actions.reduce((x, a) => x + a.freq, 0);
  if (total <= 0) return null;
  for (const a of actions) a.freq /= total;
  // 只有每个动作都有 EV 时才保留，避免一部分有一部分没有。
  if (actions.some((a) => a.ev === undefined)) for (const a of actions) delete a.ev;
  return { source: "table", actions };
}
