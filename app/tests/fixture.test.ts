import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { parseCards } from "../src/engine/cards";
import { GameState, Move, apply, defaultConfig, legalMoves, newHand, toAct } from "../src/engine/game";

/**
 * crates/solver-api 生成的对照表（`cargo run --release -p solver-api --example fixture`）：
 * 每个局面求解器树里的合法动作，规则引擎必须给出同样的动作，两边才能一一对应。
 */
interface Entry {
  players: number;
  preflop: string[];
  board: string[];
  postflop: { street: number; seat: number; kind: Move["kind"]; to: number }[];
  seat: number;
  actions: { kind: Move["kind"]; to: number }[];
}

const entries = JSON.parse(readFileSync("tests/fixtures/postflop-moves.json", "utf8")) as Entry[];
const BOARD = parseCards("Td9d6h2c5s");

function start(players: number): GameState {
  // 底牌随意，公共牌固定为对照表用的 Td 9d 6h 2c 5s。
  const rest = Array.from({ length: 52 }, (_, i) => i).filter((c) => !BOARD.includes(c));
  return newHand(defaultConfig(players), [...rest.slice(0, players * 2), ...BOARD, ...rest.slice(players * 2)]);
}

const near = (a: number, b: number) => Math.abs(a - b) <= 0.02;

describe("翻后合法动作和求解器的树一致", () => {
  it(`${entries.length} 个局面`, () => {
    for (const e of entries) {
      const where = `${e.preflop.join(", ")} / ${e.postflop.map((m) => `${m.kind} ${m.to}`).join(", ")}`;
      let s = start(e.players);
      for (const h of e.preflop) {
        const label = h.slice(h.indexOf(" ") + 1);
        s = apply(s, legalMoves(s).find((m) => m.label === label)!);
      }
      for (const pm of e.postflop) {
        const move = legalMoves(s).find((m) => m.kind === pm.kind && near(m.to, pm.to));
        expect(move, `${where}：找不到 ${pm.kind} ${pm.to}`).toBeDefined();
        s = apply(s, move!);
      }
      expect(toAct(s), where).toBe(e.seat);
      const mine = legalMoves(s);
      expect(mine.length, `${where}：${JSON.stringify(mine)}`).toBe(e.actions.length);
      e.actions.forEach((a, i) => {
        expect(mine[i].kind, where).toBe(a.kind);
        expect(near(mine[i].to, a.to), `${where}：${mine[i].to} 对 ${a.to}`).toBe(true);
      });
    }
  });
});
