/**
 * Strategy lock controls — pin the selected hand to a specific action,
 * or clear an existing lock. Only enabled in live (post-solve) mode where
 * the panel knows the underlying solver action labels.
 */

import type { PanelMeta } from "./mockData";

interface Props {
  hand: string;
  meta?: PanelMeta;
  currentLock?: number[];
  onLock: (probs: number[]) => void;
  onUnlock: () => void;
}

function eqProbs(a: number[] | undefined, b: number[]) {
  if (!a || a.length !== b.length) return false;
  return a.every((v, i) => Math.abs(v - b[i]) < 1e-6);
}

export function LockControls({ hand, meta, currentLock, onLock, onUnlock }: Props) {
  if (!meta) {
    return (
      <div className="lock-hint">
        ⓘ 节点锁定需要真实求解结果——点右上角「求解翻前」。
      </div>
    );
  }
  const n = meta.actions.length;
  return (
    <div className="lock-controls">
      <span className="lock-label">锁定 {hand}：</span>
      {meta.actions.map((label, i) => {
        const probs = Array(n).fill(0);
        probs[i] = 1.0;
        const active = eqProbs(currentLock, probs);
        return (
          <button
            key={label}
            className={`lock-btn ${active ? "active" : ""}`}
            onClick={() => onLock(probs)}
          >
            {label}
          </button>
        );
      })}
      {currentLock && (
        <button className="lock-btn lock-clear" onClick={onUnlock}>
          解除
        </button>
      )}
    </div>
  );
}
