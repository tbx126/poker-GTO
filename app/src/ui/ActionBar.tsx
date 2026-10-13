import { useEffect } from "react";
import type { Move } from "../engine/game";
import type { Strategy } from "../gto/types";
import { fmtBB } from "./colors";
import { shortLabel } from "./StrategyBars";

interface Props {
  moves: Move[];
  /** 本条街已投入，用来算“还需要放多少”。 */
  committed: number;
  hint: Strategy | null;
  onMove: (m: Move) => void;
}

/** 玩家的动作按钮，数字键 1 到 6 是快捷键；打开提示时按钮底部显示 GTO 频率。 */
export function ActionBar({ moves, committed, hint, onMove }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return;
      const k = Number(e.key);
      if (k >= 1 && k <= moves.length) onMove(moves[k - 1]);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [moves, onMove]);

  return (
    <div className="actionbar" role="group" aria-label="你的动作">
      {moves.map((m, i) => {
        const freq = hint?.actions.find((a) => a.move.kind === m.kind && a.move.to === m.to)?.freq;
        const extra = m.to - committed;
        return (
          <button key={`${m.kind}-${m.to}`} type="button" className={`act ${m.kind}`} onClick={() => onMove(m)}>
            <kbd>{i + 1}</kbd>
            <b>{m.kind === "bet" ? shortLabel(m) : m.kind === "raise" ? "加注" : m.label}</b>
            <small>{detail(m, extra)}</small>
            {freq !== undefined && (
              <>
                <em className="freq">{Math.round(freq * 100)}%</em>
                <span className="hint-fill" style={{ width: `${freq * 100}%` }} />
              </>
            )}
          </button>
        );
      })}
    </div>
  );
}

function detail(m: Move, extra: number): string {
  switch (m.kind) {
    case "fold":
      return "放弃底池";
    case "check":
      return "不加注";
    case "call":
      return `+${fmtBB(extra)}`;
    default:
      return `到 ${fmtBB(m.to)}`;
  }
}
