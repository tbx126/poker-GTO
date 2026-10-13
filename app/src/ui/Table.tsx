import type { CSSProperties } from "react";
import { GameState, Move, STREET_NAMES, pot } from "../engine/game";
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
  const lastAction = new Map<number, Move>();
  for (const e of state.events) if (e.street === street) lastAction.set(e.seat, e.move);
  const button = n === 2 ? 0 : n - 3;
  const totalPot = pot(state);
  const anim = !still;

  return (
    <div className="table-wrap">
      <div className="felt" aria-hidden="true" />

      <div className="center">
        <div className="streets" aria-label={`当前：${result ? (result.showdown ? "摊牌" : "结束") : STREET_NAMES[state.street]}`}>
          {result ? (
            <span className="on">{result.showdown ? "摊牌" : "结束"}</span>
          ) : (
            STREET_NAMES.slice(0, 4).map((name, k) => (
              <span key={name} className={k === state.street ? "on" : k < state.street ? "past" : ""}>
                {name}
              </span>
            ))
          )}
        </div>
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
        // 弃牌的对手收起底牌，只在名牌上标出来；复盘亮牌时照常显示。
        const mucked = seat.folded && !isHero && !revealAll;
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
              {!mucked && seat.cards.map((c, k) => (
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
            {action && !result ? (
              <span key={`${state.events.length}-${action.label}`} className={`bubble ${action.kind}`}>
                {action.kind === "bet" && action.fraction ? `下注 ${Math.round(action.fraction * 100)}%` : action.label}
              </span>
            ) : (
              <span className="bubble none" />
            )}
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
              <ChipStack color={action ? ACTION_COLORS[action.kind] : "var(--fold)"} />
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
