import { useEffect, useMemo, useState } from "react";
import { defaultConfig, positionName, replay, STREET_NAMES } from "../engine/game";
import { GRADE_LABELS, severity } from "../gto/coach";
import type { HandRecord } from "../store/history";
import { Verdict } from "./CoachPanel";
import { CardText } from "./PlayingCard";
import { Table } from "./Table";
import { signed } from "./colors";
import { shortLabel } from "./StrategyBars";

interface Props {
  history: HandRecord[];
  onPlay: () => void;
}

export function Review({ history, onPlay }: Props) {
  const hands = useMemo(() => [...history].reverse(), [history]);
  const [id, setId] = useState<string | null>(hands[0]?.id ?? null);
  const record = hands.find((h) => h.id === id) ?? hands[0];

  if (!record)
    return (
      <div className="view-head">
        <p className="note">还没有打完的牌。去牌桌打几手，回来就能逐街回放、找出 EV 损失最大的决策。</p>
        <button type="button" className="primary" onClick={onPlay}>
          去牌桌
        </button>
      </div>
    );

  return (
    <div className="review">
      <nav className="hand-list" aria-label="手牌历史">
        {hands.map((h) => {
          const worst = worstDecision(h);
          const hero = h.deck.slice(h.heroSeat * 2, h.heroSeat * 2 + 2);
          return (
            <button
              key={h.id}
              type="button"
              className="hand-item"
              aria-current={h.id === record.id}
              onClick={() => setId(h.id)}
            >
              <CardText cards={hero} />
              <span className="meta">
                <span>
                  {positionName(h.players, h.heroSeat)} · {h.players} 人桌
                </span>
                <small>
                  {new Date(h.at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}
                  {worst && ` · ${GRADE_LABELS[h.feedback[worst].grade]}`}
                </small>
              </span>
              <span className={`num ${h.net > 0 ? "pos" : h.net < 0 ? "neg" : ""}`}>{signed(h.net)}</span>
            </button>
          );
        })}
      </nav>
      <HandReplay key={record.id} record={record} />
    </div>
  );
}

/** 这手牌里最严重的决策（不算最佳动作），返回 moves 下标。 */
export function worstDecision(h: HandRecord): number | null {
  let worst: number | null = null;
  for (const [k, f] of Object.entries(h.feedback)) {
    if (f.grade === "best") continue;
    if (worst === null || severity(f) > severity(h.feedback[worst])) worst = Number(k);
  }
  return worst;
}

function HandReplay({ record }: { record: HandRecord }) {
  const states = useMemo(() => replay(defaultConfig(record.players), record.deck, record.moves, record.id), [record]);
  const [step, setStep] = useState(states.length - 1);
  const worst = worstDecision(record);
  const decisions = Object.keys(record.feedback)
    .map(Number)
    .sort((a, b) => a - b);
  const s = states[step];
  // 停在玩家决策之前的那一步时，显示那个决策的纠错。
  const focus = record.feedback[step];

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") setStep((x) => Math.max(0, x - 1));
      if (e.key === "ArrowRight") setStep((x) => Math.min(states.length - 1, x + 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [states.length]);

  const streetStarts = [0, 1, 2, 3].map((st) => states.findIndex((x) => x.street === st));
  const nextEvent = states[states.length - 1].events[step];

  return (
    <section className="replay">
      <Table state={s} heroSeat={record.heroSeat} handKey={record.id} revealAll still />
      <div className="scrub">
        <button type="button" className="ghost" onClick={() => setStep(0)} aria-label="回到开头">
          ⏮
        </button>
        <button type="button" className="ghost" onClick={() => setStep(Math.max(0, step - 1))} aria-label="上一步">
          ◀
        </button>
        <input
          id="replay-step"
          type="range"
          min={0}
          max={states.length - 1}
          value={step}
          onChange={(e) => setStep(Number(e.target.value))}
          aria-label="回放进度"
        />
        <button type="button" className="ghost" onClick={() => setStep(Math.min(states.length - 1, step + 1))} aria-label="下一步">
          ▶
        </button>
        <span className="num" style={{ color: "var(--muted)", minWidth: 56, textAlign: "right" }}>
          {step}/{states.length - 1}
        </span>
      </div>
      <div className="seg" role="group" aria-label="跳到某条街" style={{ justifySelf: "center" }}>
        {streetStarts.map((i, st) =>
          i >= 0 ? (
            <button key={st} type="button" aria-pressed={s.street === st && !s.result} onClick={() => setStep(i)}>
              {STREET_NAMES[st]}
            </button>
          ) : null,
        )}
        <button type="button" aria-pressed={!!s.result} onClick={() => setStep(states.length - 1)}>
          结果
        </button>
      </div>
      {nextEvent && !s.result && (
        <p className="note" style={{ justifySelf: "center" }}>
          下一步：{s.seats[nextEvent.seat].pos} {shortLabel(nextEvent.move)}
        </p>
      )}

      {focus && <Verdict f={focus} title="这一步的 GTO 策略" />}

      <h2 className="panel-title">你的决策</h2>
      {decisions.length === 0 && <p className="empty">这手牌你没有做决策（前面的人行动完之前就结束了，或者你直接在大盲位赢下盲注）。</p>}
      <div className="decisions">
        {decisions.map((k) => {
          const f = record.feedback[k];
          return (
            <button
              key={k}
              type="button"
              className={`decision${k === worst ? " worst" : ""}`}
              onClick={() => setStep(k)}
            >
              <span className="row1">
                <b className={`g-${f.grade}`}>
                  {GRADE_LABELS[f.grade]} · {STREET_NAMES[f.street]} {shortLabel(f.chosen)}
                </b>
                <span>
                  GTO 频率 {(f.freq * 100).toFixed(0)}%
                  {f.evLoss !== undefined && f.evLoss > 0 && ` · −${f.evLoss} bb`}
                  {k === worst && <> · <span className="tag-worst">损失最大</span></>}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
