/** 一张牌用 0..51 表示：点数 = c >> 2（0 是 2，12 是 A），花色 = c & 3。 */
export type Card = number;

export const RANKS = "23456789TJQKA";
export const SUITS = "cdhs";
/** 花色显示符号，顺序和 SUITS 一致。 */
export const SUIT_SYMBOLS = ["♣", "♦", "♥", "♠"];

export const rankOf = (c: Card) => c >> 2;
export const suitOf = (c: Card) => c & 3;

export function cardName(c: Card): string {
  return RANKS[rankOf(c)] + SUITS[suitOf(c)];
}

export function parseCard(s: string): Card {
  const r = RANKS.indexOf(s[0].toUpperCase());
  const u = SUITS.indexOf(s[1].toLowerCase());
  if (r < 0 || u < 0) throw new Error(`无法识别的牌：${s}`);
  return (r << 2) | u;
}

export function parseCards(s: string): Card[] {
  return (s.match(/../g) ?? []).map(parseCard);
}

/** 可重现的随机数（mulberry32），测试和复盘可以用种子还原。 */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function shuffledDeck(random: () => number = Math.random): Card[] {
  const deck = Array.from({ length: 52 }, (_, i) => i);
  for (let i = deck.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [deck[i], deck[j]] = [deck[j], deck[i]];
  }
  return deck;
}

/** 两张底牌对应的 169 种起手牌名称，例如 AKs、QJo、77。 */
export function handClass(a: Card, b: Card): string {
  let hi = rankOf(a);
  let lo = rankOf(b);
  if (lo > hi) [hi, lo] = [lo, hi];
  if (hi === lo) return RANKS[hi] + RANKS[lo];
  return RANKS[hi] + RANKS[lo] + (suitOf(a) === suitOf(b) ? "s" : "o");
}
