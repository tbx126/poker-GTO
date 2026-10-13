import { Card } from "./cards";
import { evaluate, describeHand } from "./eval";

/**
 * 2 到 6 人、固定 100bb、无抽水的现金局规则引擎。
 *
 * 翻前的合法动作和下注尺寸与 `crates/preflop/src/tree.rs` 完全一致，
 * 这样玩家走到的每个局面都能在翻前范围表里查到。翻后尺寸按需求文档：
 * 翻牌 33%、75%，转牌 50%、100%，河牌 33%、75%、150%，加注 3 倍，另有全下，不设领先下注。
 */

export interface Config {
  players: number;
  stack: number;
  smallBlind: number;
  bigBlind: number;
  open: number;
  threeBetIp: number;
  threeBetOop: number;
  fourBetIp: number;
  fourBetOop: number;
}

export function defaultConfig(players: number): Config {
  if (players < 2 || players > 6) throw new Error("只支持 2 到 6 人");
  return {
    players,
    stack: 100,
    smallBlind: 0.5,
    bigBlind: 1,
    open: 2.5,
    threeBetIp: 3,
    threeBetOop: 4,
    fourBetIp: 2.25,
    fourBetOop: 2.5,
  };
}

const NAMES = ["UTG", "HJ", "CO", "BTN", "SB", "BB"];

/** 翻前行动顺序中第 seat 个座位的位置名（最后两个是小盲和大盲）。 */
export function positionName(players: number, seat: number): string {
  if (players === 2) return ["SB", "BB"][seat];
  return NAMES[6 - players + seat];
}

/** 翻后行动顺序，数值越大越晚行动。 */
export function postflopOrder(players: number, seat: number): number {
  if (players === 2) return 1 - seat;
  if (seat === players - 2) return 0;
  if (seat === players - 1) return 1;
  return seat + 2;
}

export const STREET_NAMES = ["翻前", "翻牌", "转牌", "河牌", "摊牌"];

export const POSTFLOP_SIZES: Record<number, number[]> = {
  1: [0.33, 0.75],
  2: [0.5, 1.0],
  3: [0.33, 0.75, 1.5],
};

export type ActionKind = "fold" | "check" | "call" | "bet" | "raise" | "allin";

/** 一个合法动作。`to` 是动作之后本条街的总投入。 */
export interface Move {
  kind: ActionKind;
  to: number;
  /** 和翻前范围表一致的中文名，例如“加注到 7.5”。 */
  label: string;
  /** 翻后下注占底池的比例，用来显示“75%”这样的标签。 */
  fraction?: number;
}

export interface Seat {
  pos: string;
  /** 剩余筹码。 */
  stack: number;
  /** 本条街已投入。 */
  street: number;
  /** 整手牌已投入。 */
  total: number;
  folded: boolean;
  allIn: boolean;
  cards: Card[];
}

export interface HandEvent {
  street: number;
  seat: number;
  move: Move;
  /** 实际新放进底池的筹码。 */
  added: number;
  potBefore: number;
}

export interface Result {
  /** 每个座位从底池里拿回的筹码。 */
  won: number[];
  /** 每个座位这手牌的净输赢。 */
  net: number[];
  showdown: boolean;
  /** 摊牌时每个座位的牌型名称，弃牌的为 null。 */
  hands: (string | null)[];
}

export interface GameState {
  /** 这手牌的编号，求解器用它缓存结果。 */
  id: string;
  config: Config;
  deck: Card[];
  seats: Seat[];
  board: Card[];
  /** 0 翻前，1 翻牌，2 转牌，3 河牌，4 结束。 */
  street: number;
  bet: number;
  /** 翻前：0 未开池，1 已开池，2 已 3bet，3 已 4bet，4 有人全下。 */
  level: number;
  lastRaiser: number | null;
  callers: number;
  pending: number[];
  /** 上一条街最后主动下注的人，用来禁止领先下注。 */
  prevAggressor: number | null;
  events: HandEvent[];
  result: Result | null;
}

export const pot = (s: GameState) => s.seats.reduce((a, x) => a + x.total, 0);
export const toAct = (s: GameState): number | null => (s.result ? null : (s.pending[0] ?? null));
const round = (x: number) => Math.round(x * 100) / 100;

/** 按牌堆顺序发牌：先每人两张，再依次是翻牌、转牌、河牌。 */
export function newHand(config: Config, deck: Card[], id = ""): GameState {
  const n = config.players;
  const seats: Seat[] = Array.from({ length: n }, (_, i) => ({
    pos: positionName(n, i),
    stack: config.stack,
    street: 0,
    total: 0,
    folded: false,
    allIn: false,
    cards: [deck[i * 2], deck[i * 2 + 1]],
  }));
  const post = (i: number, amount: number) => {
    seats[i].stack -= amount;
    seats[i].street += amount;
    seats[i].total += amount;
  };
  post(n - 2, config.smallBlind);
  post(n - 1, config.bigBlind);
  return {
    id,
    config,
    deck,
    seats,
    board: [],
    street: 0,
    bet: config.bigBlind,
    level: 0,
    lastRaiser: null,
    callers: 0,
    pending: Array.from({ length: n }, (_, i) => i),
    prevAggressor: null,
    events: [],
    result: null,
  };
}

function boardFor(s: GameState, street: number): Card[] {
  const start = s.config.players * 2;
  const count = street === 0 ? 0 : street + 2;
  return s.deck.slice(start, start + count);
}

const fmt = (x: number) => String(round(x));

export function legalMoves(s: GameState): Move[] {
  const p = toAct(s);
  if (p === null) return [];
  return s.street === 0 ? preflopMoves(s, p) : postflopMoves(s, p);
}

function preflopMoves(s: GameState, p: number): Move[] {
  const c = s.config;
  const n = c.players;
  const ip = (other: number | null) =>
    other === null || postflopOrder(n, p) > postflopOrder(n, other);
  let raise: number | null = null;
  if (s.level === 0) raise = c.open;
  else if (s.level === 1)
    raise = (ip(s.lastRaiser) ? c.threeBetIp : c.threeBetOop) * s.bet + s.callers * s.bet;
  else if (s.level === 2) raise = (ip(s.lastRaiser) ? c.fourBetIp : c.fourBetOop) * s.bet;
  const moves: Move[] = [{ kind: "fold", to: s.seats[p].street, label: "弃牌" }];
  if (s.level > 0) moves.push({ kind: "call", to: Math.min(s.bet, c.stack), label: "跟注" });
  if (raise !== null) {
    if (raise < c.stack) moves.push({ kind: "raise", to: raise, label: `加注到 ${raise}` });
    else moves.push({ kind: "allin", to: c.stack, label: "全下" });
  }
  if (s.level >= 2 && s.level <= 3 && !moves.some((m) => m.kind === "allin"))
    moves.push({ kind: "allin", to: c.stack, label: "全下" });
  return moves;
}

/** 最大下注不超过底池的这个倍数时额外提供全下（和 postflop-solver 精确模式一致）。 */
const ADD_ALLIN_THRESHOLD = 1.5;
/** 下注后剩余筹码不超过（跟注后底池 × 这个值）时，直接改成全下。 */
const FORCE_ALLIN_THRESHOLD = 0.15;

function postflopMoves(s: GameState, p: number): Move[] {
  const seat = s.seats[p];
  const max = round(seat.street + seat.stack);
  const toCall = s.bet - seat.street;
  const potNow = pot(s);
  const moves: Move[] = [];
  const allin: Move = { kind: "allin", to: max, label: "全下" };
  // 下注或加注到 to 之后，如果剩下的筹码相对底池太少，就直接全下。
  const forced = (to: number) => {
    const potAfterCall = potNow + (to - seat.street) + (to - s.bet);
    return max - to <= potAfterCall * FORCE_ALLIN_THRESHOLD;
  };
  const pushAllin = (largest: number) => {
    if (moves.some((m) => m.kind === "allin")) return;
    if (max - s.bet <= (potNow + toCall) * ADD_ALLIN_THRESHOLD || largest >= max) moves.push(allin);
  };
  if (toCall <= 0) {
    moves.push({ kind: "check", to: seat.street, label: "过牌" });
    // 不设领先下注：转牌和河牌上，上一条街的进攻者还没行动时，其他人只能过牌。
    const aggressor = s.prevAggressor;
    const blocked =
      s.street >= 2 &&
      aggressor !== null &&
      aggressor !== p &&
      !s.seats[aggressor].folded &&
      !s.seats[aggressor].allIn &&
      s.pending.includes(aggressor);
    if (blocked) return moves;
    let largest = 0;
    for (const f of POSTFLOP_SIZES[s.street]) {
      // 按整数“分”计算，和求解器的整数筹码一致。
      const to = Math.round(Math.round(potNow * 100) * f) / 100;
      if (to >= max || forced(to)) {
        largest = max;
        break;
      }
      largest = to;
      moves.push({ kind: "bet", to, label: `下注 ${fmt(to)}`, fraction: f });
    }
    pushAllin(largest);
    return moves;
  }
  moves.push({ kind: "fold", to: seat.street, label: "弃牌" });
  if (toCall >= seat.stack) {
    moves.push({ kind: "call", to: max, label: "跟注全下" });
    return moves;
  }
  moves.push({ kind: "call", to: s.bet, label: "跟注" });
  // 所有对手都已全下时，加注没有意义，只剩跟注或弃牌。
  const othersCanAct = s.seats.some((x, i) => i !== p && !x.folded && !x.allIn);
  if (!othersCanAct) return moves;
  const raiseTo = round(s.bet * 3);
  if (raiseTo < max && !forced(raiseTo)) {
    moves.push({ kind: "raise", to: raiseTo, label: `加注到 ${fmt(raiseTo)}` });
    pushAllin(raiseTo);
  } else {
    moves.push(allin);
  }
  return moves;
}

/** 执行一个动作，返回新状态（不修改原状态）。 */
export function apply(prev: GameState, move: Move): GameState {
  const s: GameState = structuredClone(prev);
  const p = toAct(s);
  if (p === null) throw new Error("这手牌已经结束");
  const legal = legalMoves(prev);
  if (!legal.some((m) => m.kind === move.kind && m.to === move.to))
    throw new Error(`不合法的动作：${move.label}`);
  const seat = s.seats[p];
  const potBefore = pot(s);
  s.pending.shift();
  let added = 0;
  const putIn = (to: number) => {
    added = round(Math.min(to - seat.street, seat.stack));
    seat.stack = round(seat.stack - added);
    seat.street = round(seat.street + added);
    seat.total = round(seat.total + added);
    if (seat.stack <= 0) seat.allIn = true;
  };
  const n = s.config.players;
  const order = (from: number) => {
    const others = s.seats
      .map((_, i) => i)
      .filter((i) => i !== from && !s.seats[i].folded && !s.seats[i].allIn);
    if (s.street === 0) return others.sort((a, b) => ((a - from + n) % n) - ((b - from + n) % n));
    const key = (i: number) => (postflopOrder(n, i) - postflopOrder(n, from) + n) % n;
    return others.sort((a, b) => key(a) - key(b));
  };

  switch (move.kind) {
    case "fold":
      seat.folded = true;
      break;
    case "check":
      break;
    case "call":
      putIn(move.to);
      s.callers += 1;
      break;
    case "bet":
    case "raise":
    case "allin": {
      const to = move.kind === "allin" ? seat.street + seat.stack : move.to;
      const raised = to > s.bet;
      putIn(to);
      if (raised) {
        s.bet = seat.street;
        s.lastRaiser = p;
        s.callers = 0;
        if (s.street === 0) s.level = seat.allIn ? 4 : s.level + 1;
        s.pending = order(p);
      }
      break;
    }
  }
  s.events.push({ street: s.street, seat: p, move, added, potBefore });
  return advance(s);
}

function advance(s: GameState): GameState {
  const alive = s.seats.map((_, i) => i).filter((i) => !s.seats[i].folded);
  if (alive.length === 1) return finish(s, false);
  // 队列里可能有人已经全下（比如跟注全下），跳过。
  s.pending = s.pending.filter((i) => !s.seats[i].folded && !s.seats[i].allIn);
  if (s.pending.length > 0) return s;

  const canAct = alive.filter((i) => !s.seats[i].allIn);
  s.prevAggressor = s.lastRaiser;
  if (canAct.length <= 1 || s.street === 3) {
    s.board = boardFor(s, 3);
    return finish(s, true);
  }
  s.street += 1;
  s.board = boardFor(s, s.street);
  s.bet = 0;
  s.lastRaiser = null;
  s.callers = 0;
  for (const seat of s.seats) seat.street = 0;
  const n = s.config.players;
  s.pending = canAct.sort((a, b) => postflopOrder(n, a) - postflopOrder(n, b));
  return s;
}

function finish(s: GameState, showdown: boolean): GameState {
  const n = s.seats.length;
  const won = new Array(n).fill(0);
  const alive = s.seats.map((_, i) => i).filter((i) => !s.seats[i].folded);
  const hands: (string | null)[] = new Array(n).fill(null);
  if (!showdown) {
    won[alive[0]] = pot(s);
  } else {
    const scores = new Map<number, number>();
    for (const i of alive) {
      const cards = [...s.seats[i].cards, ...s.board];
      scores.set(i, evaluate(cards));
      hands[i] = describeHand(cards);
    }
    // 边池：按存活玩家的投入额分层，每层只有投入够多的人有资格分。
    const levels = [...new Set(alive.map((i) => s.seats[i].total))].sort((a, b) => a - b);
    let prev = 0;
    for (const level of levels) {
      const layer = s.seats.reduce((a, x) => a + Math.max(0, Math.min(x.total, level) - prev), 0);
      const eligible = alive.filter((i) => s.seats[i].total >= level);
      const best = Math.max(...eligible.map((i) => scores.get(i)!));
      const winners = eligible.filter((i) => scores.get(i) === best);
      for (const w of winners) won[w] += layer / winners.length;
      prev = level;
    }
  }
  s.street = 4;
  s.pending = [];
  s.result = {
    won: won.map(round),
    net: s.seats.map((x, i) => round(won[i] - x.total)),
    showdown,
    hands,
  };
  return s;
}

/** 翻前历史，格式和范围表 JSON 的 history 字段一致，例如 ["UTG 弃牌", "HJ 加注到 2.5"]。 */
export function preflopHistory(s: GameState): string[] {
  return s.events
    .filter((e) => e.street === 0)
    .map((e) => `${s.seats[e.seat].pos} ${e.move.label}`);
}

/** 从牌堆和动作序列重放整手牌，返回每一步之后的状态（第一个是发牌后的状态）。 */
export function replay(config: Config, deck: Card[], moves: Move[], id = ""): GameState[] {
  const states = [newHand(config, deck, id)];
  for (const m of moves) states.push(apply(states[states.length - 1], m));
  return states;
}
