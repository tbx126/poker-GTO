/**
 * 13×13 hand-class heatmap.
 *
 * Each cell is rendered as a horizontal stack of color bands, one per
 * action, with width proportional to that action's probability mass.
 * This satisfies the design guide's "single screen, simultaneous OOP/IP
 * panels with a strict color regime" requirement.
 */

import { useMemo, useState } from "react";
import { ACTIONS, type ActionKey, type HandStrategy } from "./actions";
import { ACTION_ORDER_BARS } from "./mockData";
import { buildGrid, type HandCell } from "./hands";

const ACTION_COLOR: Record<ActionKey, string> = ACTIONS.reduce(
  (acc, a) => ({ ...acc, [a.key]: a.color }),
  {} as Record<ActionKey, string>,
);

interface Props {
  strategy: Record<string, HandStrategy>;
  lockedHands?: Set<string>;
  onSelect?: (label: string, strat: HandStrategy) => void;
  selected?: string | null;
}

function StrategyCell({ cell, strat, isSelected, isLocked, onClick }: {
  cell: HandCell;
  strat: HandStrategy;
  isSelected: boolean;
  isLocked: boolean;
  onClick: () => void;
}) {
  const total = ACTION_ORDER_BARS.reduce((s, a) => s + (strat[a] ?? 0), 0) || 1;
  return (
    <div
      className={[
        "hand-cell",
        `hand-${cell.kind}`,
        isSelected ? "selected" : "",
        isLocked ? "locked" : "",
      ].filter(Boolean).join(" ")}
      onClick={onClick}
      title={cell.label + (isLocked ? " · 已锁定" : "")}
    >
      <div className="hand-bars">
        {ACTION_ORDER_BARS.map((a) => {
          const w = ((strat[a] ?? 0) / total) * 100;
          if (w < 0.5) return null;
          return (
            <div
              key={a}
              className="hand-bar"
              style={{ width: `${w}%`, background: ACTION_COLOR[a] }}
            />
          );
        })}
      </div>
      <span className="hand-label">{cell.label}</span>
    </div>
  );
}

export function RangeHeatmap({ strategy, lockedHands, onSelect, selected }: Props) {
  const cells = useMemo(buildGrid, []);
  const [internalSel, setInternalSel] = useState<string | null>(null);
  const sel = selected ?? internalSel;

  return (
    <div className="range-grid">
      {cells.map((c) => {
        const strat = strategy[c.label] ?? {};
        return (
          <StrategyCell
            key={c.label}
            cell={c}
            strat={strat}
            isSelected={sel === c.label}
            isLocked={lockedHands?.has(c.label) ?? false}
            onClick={() => {
              setInternalSel(c.label);
              onSelect?.(c.label, strat);
            }}
          />
        );
      })}
    </div>
  );
}
