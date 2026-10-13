import { useCallback, useEffect, useRef, useState } from "react";
import { shuffledDeck } from "../engine/cards";
import { GameState, Move, apply, defaultConfig, legalMoves, newHand, pot, toAct } from "../engine/game";
import { Feedback, judge, sample, strategyFor } from "../gto/coach";
import { IndexedTable, loadTable } from "../gto/preflop";
import type { Strategy } from "../gto/types";
import type { HandRecord, Settings } from "../store/history";
import { ActionBar } from "./ActionBar";
import { CoachPanel } from "./CoachPanel";
import { Table } from "./Table";
import { signed } from "./colors";

interface Hand {
  id: string;
  heroSeat: number;
  state: GameState;
  moves: Move[];
  feedback: Record<number, Feedback>;
}

const THINK_MS: Record<Settings["speed"], number> = { slow: 1100, normal: 650, fast: 220 };

function deal(players: number, heroSeat: number): Hand {
  const deck = shuffledDeck();
  return {
    id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
    heroSeat,
    state: newHand(defaultConfig(players), deck),
    moves: [],
    feedback: {},
  };
}

interface Props {
  settings: Settings;
  onHandDone: (r: HandRecord) => void;
}

export function Play({ settings, onHandDone }: Props) {
  const n = settings.players;
  const [hand, setHand] = useState<Hand>(() => deal(n, n - 1));
  // undefined：读取中；null：读取失败，翻前也用近似策略。
  const [table, setTable] = useState<IndexedTable | null | undefined>(undefined);
  const [hint, setHint] = useState<Strategy | null>(null);
  const [thinking, setThinking] = useState<{ seat: number; ms: number } | null>(null);
  const saved = useRef(new Set<string>());

  useEffect(() => {
    let live = true;
    setTable(undefined);
    loadTable(n).then(
      (t) => live && setTable(t),
      () => live && setTable(null),
    );
    if (hand.state.config.players !== n) setHand(deal(n, n - 1));
    return () => {
      live = false;
    };
    // 只在人数变化时重新发牌。
  }, [n]);

  const s = hand.state;
  const actor = toAct(s);
  const heroTurn = actor === hand.heroSeat;

  // 对手按 GTO 策略随机出牌。
  useEffect(() => {
    if (actor === null || heroTurn || table === undefined) {
      setThinking(null);
      return;
    }
    const streetChange = s.events.length > 0 && s.events[s.events.length - 1].street !== s.street;
    const ms = THINK_MS[settings.speed] + (streetChange ? 450 : 0);
    setThinking({ seat: actor, ms });
    let cancelled = false;
    const timer = setTimeout(async () => {
      const strategy = await strategyFor(s, actor, table);
      if (cancelled) return;
      const move = sample(strategy);
      setHand((h) => (h.state === s ? { ...h, state: apply(s, move), moves: [...h.moves, move] } : h));
    }, ms);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [s, actor, heroTurn, table, settings.speed]);

  // 轮到玩家时提前算好策略：打开提示就显示，做完决策后用来纠错。
  useEffect(() => {
    setHint(null);
    if (!heroTurn || table === undefined) return;
    let live = true;
    strategyFor(s, hand.heroSeat, table).then((st) => live && setHint(st));
    return () => {
      live = false;
    };
  }, [s, heroTurn, hand.heroSeat, table]);

  const onMove = useCallback(
    async (m: Move) => {
      if (toAct(s) !== hand.heroSeat) return;
      const strategy = hint ?? (await strategyFor(s, hand.heroSeat, table ?? null));
      const fb = judge(s, strategy, m, pot(s));
      setHand((h) =>
        h.state === s
          ? { ...h, state: apply(s, m), moves: [...h.moves, m], feedback: { ...h.feedback, [s.events.length]: fb } }
          : h,
      );
    },
    [s, hand.heroSeat, hint, table],
  );

  // 一手结束后存进历史。
  useEffect(() => {
    if (!s.result || saved.current.has(hand.id)) return;
    saved.current.add(hand.id);
    onHandDone({
      id: hand.id,
      at: Date.now(),
      players: n,
      heroSeat: hand.heroSeat,
      deck: s.deck,
      moves: hand.moves,
      feedback: hand.feedback,
      net: s.result.net[hand.heroSeat],
    });
  }, [s, hand, n, onHandDone]);

  const next = useCallback(() => {
    // 按钮每手顺时针移动一位，玩家的位置从大盲到小盲、按钮……依次轮转。
    setHand((h) => deal(n, (h.heroSeat - 1 + n) % n));
  }, [n]);

  useEffect(() => {
    if (!s.result) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === " " || e.key === "Enter") {
        e.preventDefault();
        next();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [s.result, next]);

  const heroNet = s.result?.net[hand.heroSeat];

  return (
    <div className="play">
      <div className="stage">
        <Table state={s} heroSeat={hand.heroSeat} handKey={hand.id} thinking={thinking} />
        {s.result ? (
          <div className="result-line">
            <span>
              这手{heroNet! > 0 ? "赢了" : heroNet! < 0 ? "输了" : "持平"}{" "}
              <span className={`num ${heroNet! > 0 ? "pos" : heroNet! < 0 ? "neg" : ""}`}>{signed(heroNet!)} bb</span>
            </span>
            <button type="button" className="primary" onClick={next}>
              下一手 <span className="num" style={{ opacity: 0.6, fontSize: 12 }}>空格</span>
            </button>
          </div>
        ) : heroTurn ? (
          <ActionBar
            moves={legalMoves(s)}
            committed={s.seats[hand.heroSeat].street}
            hint={settings.hints ? hint : null}
            onMove={onMove}
          />
        ) : (
          <div className="actionbar">
            <span className="waiting">
              {table === undefined ? "读取范围表" : `${s.seats[actor ?? 0].pos} 思考中`}
              <span className="dots">
                <i />
                <i />
                <i />
              </span>
            </span>
          </div>
        )}
      </div>
      <CoachPanel
        state={s}
        heroSeat={hand.heroSeat}
        coach={settings.coach}
        feedback={hand.feedback}
        hint={settings.hints && heroTurn ? hint : null}
      />
    </div>
  );
}
