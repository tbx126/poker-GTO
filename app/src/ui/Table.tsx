import type { CSSProperties } from "react";
import { ActionKind, GameState, STREET_NAMES, pot } from "../engine/game";
import { PlayingCard } from "./PlayingCard";
import { ACTION_COLORS, fmtBB, signed } from "./colors";

interface Props {
  state: GameState;
  heroSeat: number;
  /** 每手牌唯一的键，用来重新播放发牌动画。 */
  handKey: string;
  /** 复盘时亮出所有人的底牌。 */
  revealAll?: boolean;
  /** 正在思考的座位和思考时长（毫秒），显示倒计时条。 */
  thinking?: { seat: number; ms: number } | null;
  /** 复盘时不播放动画。 */
  still?: boolean;
}

/** 椭圆牌桌：玩家固定在正下方，其他人按行动顺序顺时针排开。 */
export function Table({ state, heroSeat, handKey, revealAll, thinking, still }: Props) {
  const n = state.config.players;
  const angle = (seat: number) => (Math.PI / 2) + (((seat - heroSeat + n) % n) * 2 * Math.PI) / n;
  const geo = (seat: number): CSSProperties =>
    ({ "--cx": Math.cos(angle(seat)), "--cy": Math.sin(angle(seat)) }) as CSSProperties;

  const result = state.result;
  const street = result ? lastStreet(state) : state.street;
  const lastAction = new Map<number, { kind: string; label: string }>();
  for (const e of state.events) if (e.street === street) lastAction.set(e.seat, e.move);
  const button = n === 2 ? 0 : n - 3;
  const totalPot = pot(state);
  const anim = !still;

  return (
    <div className="table-wrap">
      <div className="felt" aria-hidden="true">
        <div className="felt-mark">GTO · 100BB · {n} 人桌</div>
      </div>

      <div className="center">
        <div className="street-tag">{result ? (result.showdown ? "摊牌" : "结束") : STREET_NAMES[state.street]}</div>
        <div className="board" aria-label="公共牌">
          {state.board.map((c, i) => (
            <PlayingCard
              key={`${handKey}-b${c}`}
              card={c}
              anim={anim ? "flip" : undefined}
              delay={anim ? Math.max(0, i - boardStart(state.board.length)) * 110 : 0}
            />
          ))}
        </div>
        <div className="pot">
          <ChipStack color="var(--brass)" />
          <small>底池</small>
          <span>{fmtBB(totalPot)}</span>
        </div>
      </div>

      <div
        className="dealer"
        style={{
          left: `calc(50% + ${Math.cos(angle(button))} * var(--dx))`,
          top: `calc(50% + ${Math.sin(angle(button))} * var(--dy))`,
        }}
        aria-label="庄家按钮"
      >
        D
      </div>

      {state.seats.map((seat, i) => {
        const isHero = i === heroSeat;
        const showCards = isHero || revealAll || (result?.showdown && !seat.folded);
        const winner = result && result.won[i] > 0;
        const action = lastAction.get(i);
        const acting = thinking?.seat === i;
        const cls = ["seat", isHero ? "hero" : "", seat.folded ? "folded" : "", acting ? "acting" : "", winner ? "winner" : ""];
        return (
          <div
            key={i}
            className={cls.join(" ")}
            style={{ ...geo(i), left: "calc(50% + var(--cx) * var(--rx))", top: "calc(50% + var(--cy) * var(--ry))" }}
          >
            <div className="hole">
              {seat.cards.map((c, k) => (
                <PlayingCard
                  key={`${handKey}-${i}-${k}-${showCards ? "f" : "b"}`}
                  card={showCards ? c : null}
                  size={isHero ? "lg" : "sm"}
                  anim={anim ? (showCards && !isHero ? "flip" : "deal") : undefined}
                  delay={anim && !(showCards && !isHero) ? (k * n + ((i - heroSeat + n) % n)) * 70 : 0}
                  dim={seat.folded && !isHero}
                />
              ))}
            </div>
            <div className="plate">
              {action && !result && <span className={`bubble ${action.kind}`}>{action.label}</span>}
              <span className="who">
                <b>{seat.pos}</b>
                {isHero && <span className="you">你</span>}
                {seat.allIn && !result && <span>全下</span>}
              </span>
              <span className="stack">{fmtBB(seat.stack)}</span>
              {result && result.net[i] !== 0 && (
                <span className={`net-float ${result.net[i] > 0 ? "pos" : "neg"}`}>{signed(result.net[i])}</span>
              )}
              {result?.hands[i] && <span className="hand-name">{result.hands[i]}</span>}
              {acting && <span className="timer" style={{ "--think": `${thinking!.ms}ms` } as CSSProperties} />}
            </div>
          </div>
        );
      })}

      {!result &&
        state.seats.map((seat, i) => {
          if (seat.street <= 0) return null;
          const action = lastAction.get(i);
          return (
            <div
              key={`chips-${i}`}
              className="chips"
              style={{ ...geo(i), left: "calc(50% + var(--cx) * var(--bx))", top: "calc(50% + var(--cy) * var(--by))" }}
            >
              <ChipStack color={action ? ACTION_COLORS[action.kind as ActionKind] : "var(--fold)"} />
              {fmtBB(seat.street)}
            </div>
          );
        })}
    </div>
  );
}

function boardStart(len: number) {
  return len <= 3 ? 0 : len - 1;
}

function lastStreet(s: GameState) {
  return s.events.length ? s.events[s.events.length - 1].street : 0;
}

function ChipStack({ color }: { color: string }) {
  return (
    <span className="chip-stack" aria-hidden="true">
      <i style={{ "--chip": color, top: 0 } as CSSProperties} />
    </span>
  );
}
