import { useEffect, useRef } from "react";
import type { GameState } from "../engine/game";
import { STREET_NAMES } from "../engine/game";
import { Feedback, GRADE_LABELS } from "../gto/coach";
import type { SolverProgress } from "../gto/tauri";
import { SOURCE_LABELS, Strategy } from "../gto/types";
import { fmtBB } from "./colors";
import { StrategyBars, shortLabel } from "./StrategyBars";

interface Props {
  state: GameState;
  heroSeat: number;
  coach: boolean;
  /** 玩家这手牌每个决策的纠错，键是 events 下标。 */
  feedback: Record<number, Feedback>;
  /** 轮到玩家且打开了提示时的策略。 */
  hint: Strategy | null;
  /** 后台求解还没完成时的进度。 */
  progress: SolverProgress | null;
}

export function CoachPanel({ state, heroSeat, coach, feedback, hint, progress }: Props) {
  const keys = Object.keys(feedback).map(Number).sort((a, b) => a - b);
  const latest = keys.length ? feedback[keys[keys.length - 1]] : null;
  const log = useRef<HTMLDivElement>(null);
  // 新动作出现时滚到最下面。
  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight, behavior: "smooth" });
  }, [state.events.length]);

  return (
    <aside className="coach" aria-label="GTO 教练">
      {progress && <SolverBar p={progress} />}
      {hint ? (
        <section className="verdict">
          <h2>
            GTO 提示 <Source s={hint} />
          </h2>
          <StrategyBars strategy={hint} />
        </section>
      ) : coach && latest ? (
        <Verdict f={latest} />
      ) : (
        <section className="verdict">
          <h2>GTO 教练</h2>
          <p className="empty">
            {coach ? "你做出决策后，这里会显示 GTO 的动作频率和你损失的 EV。" : "纠错已关闭，打完可以在复盘里查看每个决策。"}
          </p>
        </section>
      )}

      <section className="log-section">
        <h2>本手动作</h2>
        <div className="log" ref={log}>
          {state.events.length === 0 && <p className="empty">盲注已下，等待第一个行动。</p>}
          {state.events.map((e, i) => {
            const f = feedback[i];
            return (
              <div key={i} className={`log-row${e.seat === heroSeat ? " hero" : ""}`}>
                <span className="st">{STREET_NAMES[e.street]}</span>
                <span className="who">{state.seats[e.seat].pos}</span>
                <span>{e.move.kind === "bet" && e.move.fraction ? `${shortLabel(e.move)} · ${fmtBB(e.move.to)}` : e.move.label}</span>
                {f && coach ? <span className={`dot g-${f.grade}`} title={GRADE_LABELS[f.grade]} /> : <span />}
              </div>
            );
          })}
        </div>
      </section>
    </aside>
  );
}

function SolverBar({ p }: { p: SolverProgress }) {
  return (
    <section className="solver" aria-live="polite">
      <h2>
        求解{STREET_NAMES[p.street]}
        <span className="num">{Math.round(p.fraction * 100)}%</span>
      </h2>
      <div className="solver-track">
        <span style={{ width: `${Math.max(3, p.fraction * 100)}%` }} />
      </div>
      <p className="coach-note">
        {p.iteration > 0
          ? `第 ${p.iteration} 轮，可剥削度 ${(p.exploitability * 100).toFixed(2)}% 底池，目标 0.3%`
          : "用双方走到这里的范围求解这条街"}
      </p>
    </section>
  );
}

function Source({ s }: { s: Strategy }) {
  const rough = s.source === "solver" && s.converged === false;
  return (
    <span className={`source ${rough ? "approx" : s.source}`}>
      {SOURCE_LABELS[s.source]}
      {rough && "（未收敛）"}
    </span>
  );
}

export function Verdict({ f, title = "上一个决策" }: { f: Feedback; title?: string }) {
  const same = f.chosen.kind === f.best.kind && f.chosen.to === f.best.to;
  return (
    <section className="verdict">
      <h2>
        {title} <Source s={f.strategy} />
      </h2>
      <div className="head">
        <span className={`grade g-${f.grade}`}>
          <i />
          {GRADE_LABELS[f.grade]}
        </span>
        {f.evLoss !== undefined && (
          <span className="num" style={{ color: "var(--muted)" }}>
            {f.evLoss > 0 ? `−${fmtBB(f.evLoss)} bb` : "没有损失"}
          </span>
        )}
      </div>
      <p>
        {STREET_NAMES[f.street]}你选了 <b>{shortLabel(f.chosen)}</b>，GTO 频率 {(f.freq * 100).toFixed(0)}%。
        {!same && (
          <>
            {" "}最常用的是 <b>{shortLabel(f.best)}</b>（{(f.bestFreq * 100).toFixed(0)}%）。
          </>
        )}
      </p>
      <StrategyBars strategy={f.strategy} chosen={f.chosen} />
      {f.strategy.source === "approx" && (
        <p className="coach-note">
          按胜率和底池赔率估算的近似策略
          {f.strategy.equity !== undefined && `，你对随机手牌的胜率约 ${(f.strategy.equity * 100).toFixed(0)}%`}。
        </p>
      )}
      {f.strategy.source === "solver" && f.strategy.exploitability !== undefined && (
        <p className="coach-note">
          两人底池实时求解，可剥削度 {(f.strategy.exploitability * 100).toFixed(2)}% 底池
          {f.strategy.converged === false && "（到了时间上限，没达到 0.3% 的目标，结果是近似的）"}。EV 相对于现在弃牌。
        </p>
      )}
      {f.strategy.source === "table" && f.evLoss === undefined && (
        <p className="coach-note">这份范围表只有频率，没有每个动作的 EV。</p>
      )}
      {f.strategy.source === "table" && f.evLoss !== undefined && (
        <p className="coach-note">EV 是整手牌的净输赢，已经放进底池的盲注和加注也算在内。</p>
      )}
    </section>
  );
}
