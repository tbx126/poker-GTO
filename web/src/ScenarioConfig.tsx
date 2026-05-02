/**
 * Scenario settings overlay — stack depth, blinds, and bet ladder.
 * Opens from the header pill; closes on save or backdrop click.
 */

import { useState } from "react";
import type { TreeConfig } from "./api";

interface Props {
  open: boolean;
  initial: TreeConfig;
  onClose: () => void;
  onSave: (cfg: TreeConfig) => void;
}

const PRESETS: { label: string; cfg: TreeConfig }[] = [
  { label: "100bb 现金", cfg: { stack: 100, sb_blind: 0.5, bb_blind: 1, open_to: 2.5, threebet_to: 9, fourbet_to: null } },
  { label: "50bb 中筹", cfg: { stack: 50, sb_blind: 0.5, bb_blind: 1, open_to: 2.3, threebet_to: 7, fourbet_to: null } },
  { label: "20bb 短筹", cfg: { stack: 20, sb_blind: 0.5, bb_blind: 1, open_to: 2.0, threebet_to: 5.5, fourbet_to: null } },
  { label: "200bb 深筹", cfg: { stack: 200, sb_blind: 0.5, bb_blind: 1, open_to: 3, threebet_to: 11, fourbet_to: null } },
];

export function ScenarioConfig({ open, initial, onClose, onSave }: Props) {
  const [draft, setDraft] = useState<TreeConfig>(initial);
  const [allinCheck, setAllinCheck] = useState(initial.fourbet_to === null);

  if (!open) return null;

  function set<K extends keyof TreeConfig>(key: K, value: TreeConfig[K]) {
    setDraft((d) => ({ ...d, [key]: value }));
  }

  function applyPreset(cfg: TreeConfig) {
    setDraft(cfg);
    setAllinCheck(cfg.fourbet_to === null);
  }

  function commit() {
    const final: TreeConfig = { ...draft, fourbet_to: allinCheck ? null : draft.fourbet_to };
    // Quick local validation — backend will return 422 on bad ladder anyway.
    if (!(final.sb_blind < final.bb_blind)) {
      alert("BB 必须大于 SB");
      return;
    }
    if (!(final.bb_blind <= final.open_to && final.open_to < final.threebet_to)) {
      alert("需要 BB ≤ 开池 < 3bet");
      return;
    }
    const fb = final.fourbet_to ?? final.stack;
    if (!(final.threebet_to < fb && fb <= final.stack)) {
      alert("需要 3bet < 4bet ≤ stack");
      return;
    }
    onSave(final);
  }

  return (
    <div className="console-overlay" onClick={onClose}>
      <div className="console" onClick={(e) => e.stopPropagation()} style={{ width: 540 }}>
        <div className="console-header">
          <h3>场景设置</h3>
          <button onClick={onClose}>关闭</button>
        </div>

        <div className="cfg-presets">
          <span className="cfg-label">预设：</span>
          {PRESETS.map((p) => (
            <button key={p.label} className="lock-btn" onClick={() => applyPreset(p.cfg)}>
              {p.label}
            </button>
          ))}
        </div>

        <div className="cfg-grid">
          <label>
            筹码 (bb)
            <input
              type="number"
              min={1}
              step={1}
              value={draft.stack}
              onChange={(e) => set("stack", Number(e.target.value))}
            />
          </label>
          <label>
            SB
            <input
              type="number"
              min={0.1}
              step={0.1}
              value={draft.sb_blind}
              onChange={(e) => set("sb_blind", Number(e.target.value))}
            />
          </label>
          <label>
            BB
            <input
              type="number"
              min={0.1}
              step={0.1}
              value={draft.bb_blind}
              onChange={(e) => set("bb_blind", Number(e.target.value))}
            />
          </label>
          <label>
            开池 (bb)
            <input
              type="number"
              min={0.1}
              step={0.1}
              value={draft.open_to}
              onChange={(e) => set("open_to", Number(e.target.value))}
            />
          </label>
          <label>
            3bet 到 (bb)
            <input
              type="number"
              min={0.1}
              step={0.5}
              value={draft.threebet_to}
              onChange={(e) => set("threebet_to", Number(e.target.value))}
            />
          </label>
          <label>
            4bet 到 (bb)
            <input
              type="number"
              min={0.1}
              step={1}
              value={draft.fourbet_to ?? draft.stack}
              disabled={allinCheck}
              onChange={(e) => set("fourbet_to", Number(e.target.value))}
            />
          </label>
          <label className="cfg-allin">
            <input
              type="checkbox"
              checked={allinCheck}
              onChange={(e) => setAllinCheck(e.target.checked)}
            />
            <span>4bet 直接 all-in（= stack）</span>
          </label>
        </div>

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={onClose}>取消</button>
          <button className="primary" onClick={commit}>
            应用
          </button>
        </div>
      </div>
    </div>
  );
}
