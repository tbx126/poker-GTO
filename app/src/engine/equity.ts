import { Card } from "./cards";
import { evaluate } from "./eval";

/**
 * 蒙特卡洛估算胜率：自己的两张牌对 `opponents` 个随机手牌，公共牌补齐到五张。
 * 平分底池按份额计入。
 */
export function equity(
  hole: Card[],
  board: Card[],
  opponents: number,
  iterations = 600,
  random: () => number = Math.random,
): number {
  if (opponents <= 0) return 1;
  const dead = new Set([...hole, ...board]);
  const live: Card[] = [];
  for (let c = 0; c < 52; c++) if (!dead.has(c)) live.push(c);
  const need = 5 - board.length + opponents * 2;
  const pool = live.slice();
  const cards = new Array<Card>(7);
  let total = 0;
  for (let it = 0; it < iterations; it++) {
    // 部分洗牌：只把需要的前 need 张随机化。
    for (let i = 0; i < need; i++) {
      const j = i + Math.floor(random() * (pool.length - i));
      const t = pool[i];
      pool[i] = pool[j];
      pool[j] = t;
    }
    const runout = board.concat(pool.slice(0, 5 - board.length));
    cards[0] = hole[0];
    cards[1] = hole[1];
    for (let k = 0; k < 5; k++) cards[k + 2] = runout[k];
    const mine = evaluate(cards);
    let ties = 1;
    let lost = false;
    for (let o = 0; o < opponents; o++) {
      cards[0] = pool[5 - board.length + o * 2];
      cards[1] = pool[5 - board.length + o * 2 + 1];
      const theirs = evaluate(cards);
      if (theirs > mine) {
        lost = true;
        break;
      }
      if (theirs === mine) ties++;
    }
    if (!lost) total += 1 / ties;
  }
  return total / iterations;
}
