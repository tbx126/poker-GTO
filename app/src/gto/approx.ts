import { equity } from "../engine/equity";
import { GameState, legalMoves, pot, postflopOrder } from "../engine/game";
import type { ActionAdvice, Strategy } from "./types";

/**
 * 规则近似策略：用胜率和底池赔率估算每个动作的 EV，再按 EV 做 softmax 得到混合频率。
 *
 * 用在多人底池（需求文档规定用规则近似并标注“近似”），以及翻后求解器还没接入时的两人底池。
 * - 被跟注时的胜率会按下注占底池的比例打折，模拟对手跟注范围更强。
 * - 对手按最小防守频率（MDF）弃牌，多人时要所有人都弃牌。
 * - 没位置一方的实现率更低。
 */
export function approxStrategy(s: GameState, seat: number, iterations = 500): Strategy {
  const me = s.seats[seat];
  const n = s.config.players;
  const alive = s.seats.map((_, i) => i).filter((i) => !s.seats[i].folded);
  const opponents = alive.filter((i) => i !== seat);
  const eq = equity(me.cards, s.board, opponents.length, iterations);
  const p = pot(s);
  const toCall = Math.max(0, s.bet - me.street);
  const lastToAct = opponents.every((o) => postflopOrder(n, o) < postflopOrder(n, seat));
  const realization = s.street === 3 ? 1 : lastToAct ? 0.95 : 0.8;

  const actions: ActionAdvice[] = legalMoves(s).map((move) => {
    const added = move.to - me.street;
    let ev: number;
    switch (move.kind) {
      case "fold":
        ev = 0;
        break;
      case "check":
        ev = eq * p * realization;
        break;
      case "call": {
        const pressure = Math.min(2, toCall / Math.max(p - toCall, 0.5));
        const eqCalled = eq ** (1 + 0.5 * pressure);
        const r = me.stack <= toCall ? 1 : realization;
        ev = eqCalled * (p + added) * r - added;
        break;
      }
      default: {
        // 对手需要再跟 x，看到的底池是 p + added。
        const x = move.to - s.bet;
        const foldEach = Math.min(0.85, (x / (p + added)) * 0.95);
        const foldAll = foldEach ** opponents.length;
        const pressure = Math.min(2, x / Math.max(p, 0.5));
        const eqCalled = eq ** (1 + 0.6 * pressure);
        const r = move.kind === "allin" ? 1 : realization;
        ev = foldAll * p + (1 - foldAll) * (eqCalled * (p + added + x) * r - added);
      }
    }
    return { move, freq: 0, ev: Math.round(ev * 100) / 100 };
  });

  // EV 越接近最好的动作，频率越高；温度随底池变化，底池越大混合越少。
  const best = Math.max(...actions.map((a) => a.ev!));
  const temperature = Math.max(0.04 * p, 0.08);
  for (const a of actions) a.freq = Math.exp((a.ev! - best) / temperature);
  normalize(actions);
  for (const a of actions) if (a.freq < 0.02) a.freq = 0;
  normalize(actions);
  return { source: "approx", actions, equity: eq };
}

function normalize(actions: ActionAdvice[]) {
  const total = actions.reduce((x, a) => x + a.freq, 0) || 1;
  for (const a of actions) a.freq /= total;
}
