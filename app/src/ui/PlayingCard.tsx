import { Card, RANKS, SUIT_SYMBOLS, rankOf, suitOf } from "../engine/cards";

interface Props {
  card?: Card | null;
  size?: "xs" | "sm" | "md" | "lg";
  /** 发牌或翻牌动画，delay 单位毫秒。 */
  anim?: "deal" | "flip";
  delay?: number;
  dim?: boolean;
}

/** 一张牌；card 为空时显示牌背。 */
export function PlayingCard({ card, size = "md", anim, delay = 0, dim }: Props) {
  const cls = ["card", size === "md" ? "" : size, anim ?? "", dim ? "dim" : ""];
  const style = anim ? { animationDelay: `${delay}ms` } : undefined;
  if (card === undefined || card === null)
    return <div className={[...cls, "back"].join(" ")} style={style} aria-label="牌背" />;
  const r = RANKS[rankOf(card)];
  const s = SUIT_SYMBOLS[suitOf(card)];
  const rank = r === "T" ? "10" : r;
  return (
    <div className={[...cls, `suit-${suitOf(card)}`].join(" ")} style={style} aria-label={`${rank}${s}`}>
      <span className="r">{rank}</span>
      <span className="s">{s}</span>
      <span className="big" aria-hidden="true">{s}</span>
    </div>
  );
}

export function CardText({ cards }: { cards: Card[] }) {
  return (
    <span className="mini-cards">
      {cards.map((c) => (
        <PlayingCard key={c} card={c} size="xs" />
      ))}
    </span>
  );
}
