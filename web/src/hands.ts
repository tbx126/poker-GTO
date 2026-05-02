/**
 * 13×13 hand-class grid. Convention: rows = first card (high), columns = second.
 *
 *   row=0,col=0  → AA       (pair)
 *   row=0,col=1  → AKs      (suited, above diagonal)
 *   row=1,col=0  → AKo      (offsuit, below diagonal)
 */

export const RANK_LABELS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"] as const;
export type RankLabel = (typeof RANK_LABELS)[number];

export type HandKind = "pair" | "suited" | "offsuit";

export interface HandCell {
  row: number;       // 0..12
  col: number;       // 0..12
  label: string;     // e.g. "AKs", "AKo", "AA"
  kind: HandKind;
}

export function handLabel(row: number, col: number): string {
  const r1 = RANK_LABELS[Math.min(row, col)];
  const r2 = RANK_LABELS[Math.max(row, col)];
  if (row === col) return `${r1}${r2}`;
  return `${r1}${r2}${col > row ? "s" : "o"}`;
}

export function buildGrid(): HandCell[] {
  const cells: HandCell[] = [];
  for (let row = 0; row < 13; row++) {
    for (let col = 0; col < 13; col++) {
      cells.push({
        row,
        col,
        label: handLabel(row, col),
        kind: row === col ? "pair" : col > row ? "suited" : "offsuit",
      });
    }
  }
  return cells;
}
