import type { Move } from "../engine/game";
import type { Strategy } from "../gto/types";
import { fmtBB, moveColor } from "./colors";

interface Props {
  strategy: Strategy;
  chosen?: Move;
}

/** 每个动作一行：GTO 频率条，有 EV 时在最右边一列写出 EV。 */
export function StrategyBars({ strategy, chosen }: Props) {
  let sizeRank = 0;
  const hasEv = strategy.actions.every((a) => a.ev !== undefined);
  return (
    <div className={`bars${hasEv ? " with-ev" : ""}`}>
      {hasEv && (
        <div className="bar cols" aria-hidden="true">
          <span />
          <span>GTO 频率</span>
          <span />
          <span>EV（bb）</span>
        </div>
      )}
      {strategy.actions.map((a) => {
        const rank = a.move.kind === "bet" || a.move.kind === "raise" ? sizeRank++ : 0;
        const isChosen = chosen && chosen.kind === a.move.kind && chosen.to === a.move.to;
        return (
          <div key={`${a.move.kind}-${a.move.to}`} className={`bar${isChosen ? " chosen" : ""}`}>
            <span className="label" title={a.move.label}>
              {shortLabel(a.move)}
            </span>
            <span className="track">
              <span className="fill" style={{ display: "block", width: `${a.freq * 100}%`, background: moveColor(a.move.kind, rank) }} />
            </span>
            <span className="val">{(a.freq * 100).toFixed(0)}%</span>
            {hasEv && <span className={`ev${a.ev! > 0 ? " pos" : ""}`}>{a.ev! >= 0 ? "+" : ""}{fmtBB(a.ev!)}</span>}
          </div>
        );
      })}
    </div>
  );
}

export function shortLabel(m: Move): string {
  if (m.fraction !== undefined) return `下注 ${Math.round(m.fraction * 100)}%`;
  return m.label;
}
