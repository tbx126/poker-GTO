import type { Move } from "../engine/game";
import type { Strategy } from "../gto/types";
import { fmtBB, moveColor } from "./colors";

interface Props {
  strategy: Strategy;
  chosen?: Move;
}

/** 每个动作一行：GTO 频率条，有 EV 时在下面写出 EV。 */
export function StrategyBars({ strategy, chosen }: Props) {
  let sizeRank = 0;
  return (
    <div className="bars">
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
            {a.ev !== undefined && <span className="ev">EV {a.ev >= 0 ? "+" : ""}{fmtBB(a.ev)} bb</span>}
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
