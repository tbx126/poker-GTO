import { describe, expect, it } from "vitest";
import { parseCards, rng, shuffledDeck } from "../src/engine/cards";
import { apply, defaultConfig, legalMoves, newHand, pot } from "../src/engine/game";
import { judge, mapSolverActions, sample, severity } from "../src/gto/coach";
import { handState } from "../src/gto/tauri";
import type { Strategy } from "../src/gto/types";

const s = newHand(defaultConfig(6), shuffledDeck(rng(3)));
const [fold, raise] = legalMoves(s);

describe("纠错", () => {
  it("按频率评级（范围表没有 EV）", () => {
    const st: Strategy = { source: "table", actions: [{ move: fold, freq: 0.97 }, { move: raise, freq: 0.03 }] };
    expect(judge(s, st, fold, pot(s)).grade).toBe("best");
    const off = judge(s, st, raise, pot(s));
    expect(off.grade).toBe("mistake");
    expect(off.evLoss).toBeUndefined();
    expect(severity(off)).toBeGreaterThan(0);
  });

  it("有 EV 时按损失占底池的比例评级", () => {
    const st: Strategy = {
      source: "approx",
      actions: [
        { move: fold, freq: 0.1, ev: 0 },
        { move: raise, freq: 0.9, ev: 1.5 },
      ],
    };
    const f = judge(s, st, fold, 1.5);
    expect(f.evLoss).toBe(1.5);
    expect(f.grade).toBe("blunder");
    expect(judge(s, st, raise, 1.5).grade).toBe("best");
  });

  it("按频率抽样", () => {
    const st: Strategy = { source: "table", actions: [{ move: fold, freq: 0.25 }, { move: raise, freq: 0.75 }] };
    const random = rng(4);
    let raises = 0;
    for (let i = 0; i < 4000; i++) if (sample(st, random).kind === "raise") raises++;
    expect(raises / 4000).toBeGreaterThan(0.72);
    expect(raises / 4000).toBeLessThan(0.78);
  });
});

describe("求解器结果对应到合法动作", () => {
  it("下注按最接近的金额对应，对不上的动作不列出", () => {
    // 两人：SB 开池，BB 跟注，翻牌 BB 先行动，可以过牌或下注 33%、75%。
    let h = newHand(defaultConfig(2), shuffledDeck(rng(8)), "t");
    const pick = (kind: string) => (h = apply(h, legalMoves(h).find((m) => m.kind === kind)!));
    pick("raise");
    pick("call");
    const legal = legalMoves(h);
    const bet33 = legal.find((m) => m.kind === "bet")!;
    const st = mapSolverActions(h, [
      { kind: "check", to: 0, freq: 0.5, ev: 1.2 },
      { kind: "bet", to: bet33.to + 0.03, freq: 0.3, ev: 1.25 },
      { kind: "bet", to: bet33.to - 0.02, freq: 0.1, ev: 1.15 },
      { kind: "fold", to: 0, freq: 0.1, ev: 0 },
    ], 0.002);
    expect(st.source).toBe("solver");
    expect(st.actions.map((a) => a.move.kind)).toEqual(["check", "bet"]);
    expect(st.actions[1].move).toEqual(bet33);
    expect(st.actions[0].freq).toBeCloseTo(0.5 / 0.9, 6);
    expect(st.actions[1].ev).toBeCloseTo(1.225, 1);
    // 选了策略里没有的 75% 下注：没有 EV，按频率 0 评级。
    const off = judge(h, st, legal.find((m) => m.kind === "bet" && m.to !== bet33.to)!, pot(h));
    expect(off.evLoss).toBeUndefined();
    expect(off.grade).toBe("blunder");
  });

  it("转换成求解接口的 HandState", () => {
    let h = newHand(defaultConfig(2), parseCards("AsKsQh2dTd9d6h3c4d"), "hand-1");
    const pick = (kind: string) => (h = apply(h, legalMoves(h).find((m) => m.kind === kind)!));
    pick("raise");
    pick("call");
    pick("check");
    expect(handState(h)).toEqual({
      handId: "hand-1",
      players: 2,
      preflop: ["SB 加注到 2.5", "BB 跟注"],
      board: ["Td", "9d", "6h"],
      postflop: [{ street: 1, seat: 1, kind: "check", to: 0 }],
      cards: [["As", "Ks"], ["Qh", "2d"]],
    });
  });
});
