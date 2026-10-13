import type { ActionKind } from "../engine/game";

export const ACTION_COLORS: Record<ActionKind, string> = {
  fold: "var(--fold)",
  check: "var(--check)",
  call: "var(--call)",
  bet: "var(--raise)",
  raise: "var(--raise)",
  allin: "var(--allin)",
};

/** 同一局面里有多个下注尺寸时，大尺寸用深一点的红色。 */
export function moveColor(kind: ActionKind, sizeRank = 0): string {
  if ((kind === "bet" || kind === "raise") && sizeRank > 0) return "var(--raise2)";
  return ACTION_COLORS[kind];
}

export const fmtBB = (x: number) => {
  const v = Math.round(x * 100) / 100;
  return Number.isInteger(v) ? String(v) : v.toFixed(v * 10 === Math.round(v * 10) ? 1 : 2);
};

export const signed = (x: number) => (x > 0 ? "+" : "") + fmtBB(x);
