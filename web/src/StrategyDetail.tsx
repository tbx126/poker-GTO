/** Right-side detail strip — shows the highlighted hand's frequency mix. */

import { ACTIONS, type HandStrategy } from "./actions";
import { LockControls } from "./LockControls";
import type { PanelMeta } from "./mockData";

interface Props {
  hand: string | null;
  strategy: HandStrategy | null;
  meta?: PanelMeta;
  currentLock?: number[];
  onLock?: (probs: number[]) => void;
  onUnlock?: () => void;
}

export function StrategyDetail({ hand, strategy, meta, currentLock, onLock, onUnlock }: Props) {
  if (!hand || !strategy) {
    return (
      <div className="detail-empty">
        点选热力图中的牌型查看详细动作频率。
      </div>
    );
  }
  const total = ACTIONS.reduce((s, a) => s + (strategy[a.key] ?? 0), 0) || 1;
  return (
    <div className="detail">
      <div className="detail-hand">{hand}</div>
      <div className="detail-actions">
        {ACTIONS.map((a) => {
          const p = strategy[a.key] ?? 0;
          if (p < 0.005) return null;
          const pct = (p / total) * 100;
          return (
            <div key={a.key} className="detail-row">
              <span className="dot" style={{ background: a.color }} />
              <span className="action-name">{a.label}</span>
              <div className="bar-track">
                <div className="bar-fill" style={{ width: `${pct}%`, background: a.color }} />
              </div>
              <span className="pct">{pct.toFixed(1)}%</span>
            </div>
          );
        })}
      </div>
      {onLock && onUnlock && (
        <LockControls
          hand={hand}
          meta={meta}
          currentLock={currentLock}
          onLock={onLock}
          onUnlock={onUnlock}
        />
      )}
    </div>
  );
}
