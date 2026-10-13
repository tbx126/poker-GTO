import { Card, rankOf, suitOf } from "./cards";

/** 牌型类别，数值越大越强。 */
export const CATEGORY_NAMES = ["高牌", "一对", "两对", "三条", "顺子", "同花", "葫芦", "四条", "同花顺"];

const highBits = (mask: number, n: number): number[] => {
  const out: number[] = [];
  for (let r = 12; r >= 0 && out.length < n; r--) if (mask & (1 << r)) out.push(r);
  return out;
};

/** 点数位掩码里最高的顺子，返回顶张点数，没有返回 -1。A 可以当 1 用。 */
function straightTop(mask: number): number {
  // 整体左移一位，位 0 放“当 1 用的 A”，再找连续 5 位。
  const shifted = ((mask << 1) | ((mask >> 12) & 1)) & 0x3fff;
  for (let top = 13; top >= 4; top--) {
    const window = 0x1f << (top - 4);
    if ((shifted & window) === window) return top - 1;
  }
  return -1;
}

const score = (category: number, kickers: number[]) => {
  let s = category;
  for (let i = 0; i < 5; i++) s = s * 16 + (kickers[i] ?? 0);
  return s;
};

/** 5 到 7 张牌里最好的五张牌的分数，分数越大越强。 */
export function evaluate(cards: Card[]): number {
  const counts = new Array(13).fill(0);
  const suitMasks = [0, 0, 0, 0];
  let rankMask = 0;
  for (const c of cards) {
    const r = rankOf(c);
    counts[r]++;
    suitMasks[suitOf(c)] |= 1 << r;
    rankMask |= 1 << r;
  }

  for (const mask of suitMasks) {
    if (popcount(mask) >= 5) {
      const top = straightTop(mask);
      if (top >= 0) return score(8, [top]);
      return score(5, highBits(mask, 5));
    }
  }

  let quad = -1;
  const trips: number[] = [];
  const pairs: number[] = [];
  for (let r = 12; r >= 0; r--) {
    if (counts[r] === 4) quad = r;
    else if (counts[r] === 3) trips.push(r);
    else if (counts[r] === 2) pairs.push(r);
  }
  if (quad >= 0) return score(7, [quad, ...highBits(rankMask & ~(1 << quad), 1)]);
  if (trips.length && (trips.length > 1 || pairs.length)) {
    const pair = Math.max(trips[1] ?? -1, pairs[0] ?? -1);
    return score(6, [trips[0], pair]);
  }
  const top = straightTop(rankMask);
  if (top >= 0) return score(4, [top]);
  if (trips.length) return score(3, [trips[0], ...highBits(rankMask & ~(1 << trips[0]), 2)]);
  if (pairs.length >= 2) {
    const [a, b] = pairs;
    return score(2, [a, b, ...highBits(rankMask & ~(1 << a) & ~(1 << b), 1)]);
  }
  if (pairs.length) return score(1, [pairs[0], ...highBits(rankMask & ~(1 << pairs[0]), 3)]);
  return score(0, highBits(rankMask, 5));
}

export function categoryOf(scoreValue: number): number {
  return Math.floor(scoreValue / 16 ** 5);
}

export function describeHand(cards: Card[]): string {
  return CATEGORY_NAMES[categoryOf(evaluate(cards))];
}

function popcount(x: number): number {
  let n = 0;
  while (x) {
    x &= x - 1;
    n++;
  }
  return n;
}
