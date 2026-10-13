import type { GameState } from "../engine/game";
import { STREET_NAMES } from "../engine/game";
import { Feedback, GRADE_LABELS } from "../gto/coach";
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
}

export function CoachPanel({ state, heroSeat, coach, feedback, hint }: Props) {
  const keys = Object.keys(feedback).map(Number).sort((a, b) => a - b);
  const latest = keys.length ? feedback[keys[keys.length - 1]] : null;

  return (
    <aside className="coach" aria-label="GTO 教练">
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

      <section>
        <h2>本手动作</h2>
        <div className="log">
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

function Source({ s }: { s: Strategy }) {
  return <span className={`source ${s.source}`}>{SOURCE_LABELS[s.source]}</span>;
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
      {f.strategy.source === "table" && f.evLoss === undefined && (
        <p className="coach-note">这份范围表只有频率，没有每个动作的 EV。</p>
      )}
      {f.strategy.source === "table" && f.evLoss !== undefined && (
        <p className="coach-note">EV 是整手牌的净输赢，已经放进底池的盲注和加注也算在内。</p>
      )}
    </section>
  );
}
