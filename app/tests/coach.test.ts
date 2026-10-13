import { describe, expect, it } from "vitest";
import { rng, shuffledDeck } from "../src/engine/cards";
import { defaultConfig, legalMoves, newHand, pot } from "../src/engine/game";
import { judge, sample, severity } from "../src/gto/coach";
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
