import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { parseCards, rng, shuffledDeck } from "../src/engine/cards";
import { equity } from "../src/engine/equity";
import { categoryOf, evaluate } from "../src/engine/eval";
import { apply, defaultConfig, legalMoves, newHand, pot, replay, toAct } from "../src/engine/game";
import { approxStrategy } from "../src/gto/approx";
import { index, lookupPreflop, RangeTable } from "../src/gto/preflop";

const cat = (s: string) => categoryOf(evaluate(parseCards(s)));

describe("牌型评估", () => {
  it("识别各种牌型", () => {
    expect(cat("AsKsQsJsTs2c3d")).toBe(8);
    expect(cat("5h4h3h2hAh9c9d")).toBe(8);
    expect(cat("9c9d9h9sKd2c3c")).toBe(7);
    expect(cat("9c9d9hKsKd2c3c")).toBe(6);
    expect(cat("2h7h9hJhKh2c3c")).toBe(5);
    expect(cat("As2d3c4h5sKdKc")).toBe(4);
    expect(cat("9c9d9hKs2d3c7c")).toBe(3);
    expect(cat("9c9dKhKs2d3c7c")).toBe(2);
    expect(cat("9c9dAhKs2d3c7c")).toBe(1);
    expect(cat("9c8dAhKs2d3c6c")).toBe(0);
  });

  it("比较大小和踢脚", () => {
    expect(evaluate(parseCards("AsAdKc7h2s"))).toBeGreaterThan(evaluate(parseCards("AhAcQd7c2d")));
    expect(evaluate(parseCards("6s5d4c3h2s"))).toBeGreaterThan(evaluate(parseCards("5s4d3c2hAs")));
    expect(evaluate(parseCards("KsKdKc2h2s"))).toBeGreaterThan(evaluate(parseCards("QsQdQcAhAs")));
  });

  it("AA 对 72o 的胜率约 88%", () => {
    const e = equity(parseCards("AsAh"), [], 1, 4000, rng(1));
    expect(e).toBeGreaterThan(0.84);
    expect(e).toBeLessThan(0.91);
  });
});

describe("规则引擎", () => {
  it("全部弃牌给大盲", () => {
    let s = newHand(defaultConfig(6), shuffledDeck(rng(2)));
    while (toAct(s) !== null) s = apply(s, legalMoves(s)[0]);
    expect(s.result!.net[5]).toBe(0.5);
    expect(s.result!.net[4]).toBe(-0.5);
  });

  it("随机对局里筹码守恒，每手都能打完", () => {
    const random = rng(7);
    for (let hand = 0; hand < 400; hand++) {
      const players = 2 + (hand % 5);
      let s = newHand(defaultConfig(players), shuffledDeck(random));
      let steps = 0;
      while (toAct(s) !== null) {
        const moves = legalMoves(s);
        expect(moves.length).toBeGreaterThan(0);
        s = apply(s, moves[Math.floor(random() * moves.length)]);
        expect(++steps).toBeLessThan(200);
      }
      const r = s.result!;
      expect(Math.abs(r.net.reduce((a, b) => a + b, 0))).toBeLessThan(1e-6);
      expect(r.won.reduce((a, b) => a + b, 0)).toBeCloseTo(pot(s), 6);
      for (const seat of s.seats) expect(seat.stack).toBeGreaterThanOrEqual(-1e-9);
    }
  });

  it("边池：短码全下只能赢自己那一层", () => {
    // 两人：SB 拿 AA，BB 拿 KK，公共牌没帮任何人。
    const deck = parseCards("AsAhKsKh2c7d9hJc3s");
    const config = { ...defaultConfig(2) };
    let s = newHand(config, [...deck, ...shuffledDeck(rng(3)).filter((c) => !deck.includes(c))]);
    s = apply(s, legalMoves(s).find((m) => m.kind === "raise")!);
    s = apply(s, legalMoves(s).find((m) => m.kind === "raise")!);
    s = apply(s, legalMoves(s).find((m) => m.kind === "allin")!);
    s = apply(s, legalMoves(s).find((m) => m.kind === "call")!);
    expect(s.result!.showdown).toBe(true);
    expect(s.result!.net).toEqual([100, -100]);
  });

  it("重放得到同样的结果", () => {
    const random = rng(11);
    const deck = shuffledDeck(random);
    const moves = [];
    let s = newHand(defaultConfig(4), deck);
    while (toAct(s) !== null) {
      const m = legalMoves(s)[Math.floor(random() * legalMoves(s).length)];
      moves.push(m);
      s = apply(s, m);
    }
    const states = replay(defaultConfig(4), deck, moves);
    expect(states[states.length - 1].result).toEqual(s.result);
  });

  it("转牌上不能领先下注", () => {
    // 两人：SB 开池，BB 跟注；翻牌 BB 过牌，SB 下注，BB 跟注；转牌 BB 只能过牌。
    let s = newHand(defaultConfig(2), shuffledDeck(rng(5)));
    const pick = (kind: string) => (s = apply(s, legalMoves(s).find((m) => m.kind === kind)!));
    pick("raise");
    pick("call");
    expect(s.street).toBe(1);
    expect(legalMoves(s).map((m) => m.kind)).toContain("bet");
    pick("check");
    pick("bet");
    pick("call");
    expect(s.street).toBe(2);
    expect(legalMoves(s).map((m) => m.kind)).toEqual(["check"]);
  });
});

describe("翻前动作和范围表一致", () => {
  for (const n of [2, 3, 4, 5, 6]) {
    it(`${n} 人桌每个局面的动作都对得上`, () => {
      const table = JSON.parse(readFileSync(`public/ranges/${n}max.json`, "utf8")) as RangeTable;
      const t = index(table);
      for (const spot of table.spots) {
        let s = newHand(defaultConfig(n), shuffledDeck(rng(1)));
        for (const h of spot.history) {
          const label = h.slice(h.indexOf(" ") + 1);
          const move = legalMoves(s).find((m) => m.label === label);
          expect(move, `${spot.history.join(", ")} 里的 ${h}`).toBeDefined();
          s = apply(s, move!);
        }
        expect(s.seats[toAct(s)!].pos).toBe(spot.actor);
        expect(legalMoves(s).map((m) => m.label)).toEqual(spot.actions);
        const strategy = lookupPreflop(t, s, toAct(s)!);
        expect(strategy).not.toBeNull();
      }
    });
  }
});

describe("近似策略", () => {
  it("河牌拿坚果时不弃牌，频率加起来是 1", () => {
    // SB 拿 AsKs，BB 拿 Qh2d，公共牌 QsJsTs3c4d：SB 是皇家同花顺。
    const fixed = parseCards("AsKsQh2dQsJsTs3c4d");
    const deck = [...fixed, ...shuffledDeck(rng(9)).filter((c) => !fixed.includes(c))];
    let s = newHand(defaultConfig(2), deck);
    const pick = (kind: string) => (s = apply(s, legalMoves(s).find((m) => m.kind === kind)!));
    pick("raise");
    pick("call");
    for (let i = 0; i < 4; i++) pick("check");
    expect(s.street).toBe(3);
    pick("check");
    // 轮到 SB，面对过牌。
    const strategy = approxStrategy(s, toAct(s)!, 300);
    expect(strategy.actions.reduce((a, x) => a + x.freq, 0)).toBeCloseTo(1, 6);
    expect(strategy.equity).toBe(1);
    const check = strategy.actions.find((a) => a.move.kind === "check")!;
    expect(check.freq).toBeLessThan(0.5);
  });
});
