import { useEffect, useMemo, useRef, useState } from "react";
import { IndexedTable, Spot, loadTable, saveCustom, validateTable } from "../gto/preflop";

const SIZES = [2, 3, 4, 5, 6];
const RANKS = "AKQJT98765432";
const GROUPS = ["首个入池", "面对开池", "面对再加注"];

function actionColor(label: string, actions: string[]) {
  if (label === "弃牌") return "var(--fold)";
  if (label === "跟注") return "var(--call)";
  if (label === "全下") return "var(--allin)";
  const raises = actions.filter((a) => a.startsWith("加注"));
  return raises.indexOf(label) > 0 ? "var(--raise2)" : "var(--raise)";
}

const combos = (name: string) => (name.length === 2 ? 6 : name[2] === "s" ? 4 : 12);

function describe(spot: Spot) {
  const acts = spot.history.filter((h) => !h.endsWith("弃牌"));
  const raises = acts.filter((h) => /加注|全下/.test(h)).length;
  const group = acts.length === 0 ? GROUPS[0] : raises === 1 ? GROUPS[1] : GROUPS[2];
  const story = acts.length ? acts.map((h) => h.replace("加注到", "加注")).join("，") : "前面的人都弃牌";
  return { group, story };
}

export function Ranges({ initialPlayers }: { initialPlayers: number }) {
  const [size, setSize] = useState(initialPlayers);
  const [data, setData] = useState<IndexedTable | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [spotIndex, setSpotIndex] = useState(0);
  const [detail, setDetail] = useState("点一下或悬停在格子上查看这手牌的具体频率。");
  const [version, setVersion] = useState(0);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let live = true;
    setData(null);
    loadTable(size).then(
      (t) => {
        if (!live) return;
        setData(t);
        setError(null);
      },
      (e: Error) => live && setError(e.message),
    );
    return () => {
      live = false;
    };
  }, [size, version]);

  const items = useMemo(() => {
    if (!data) return [];
    const pos = data.table.positions;
    return data.table.spots
      .map((s, i) => ({ s, i, ...describe(s) }))
      .sort(
        (a, b) =>
          GROUPS.indexOf(a.group) - GROUPS.indexOf(b.group) ||
          pos.indexOf(a.s.actor) - pos.indexOf(b.s.actor) ||
          b.s.reach - a.s.reach,
      );
  }, [data]);

  useEffect(() => {
    if (items.length) setSpotIndex(items[0].i);
  }, [items]);

  async function importFile(file: File) {
    try {
      const table = validateTable(JSON.parse(await file.text()), size);
      saveCustom(size, table);
      setError(null);
      setVersion((v) => v + 1);
    } catch (e) {
      setError(e instanceof SyntaxError ? "文件不是合法的 JSON" : (e as Error).message);
    }
  }

  const spot = data?.table.spots[spotIndex];

  return (
    <div className="ranges">
      <div style={{ display: "grid", gap: 12, minWidth: 0 }}>
        <div className="seg" role="group" aria-label="桌型">
          {SIZES.map((n) => (
            <button key={n} type="button" aria-pressed={n === size} onClick={() => setSize(n)}>
              {n} 人
            </button>
          ))}
        </div>
        <nav className="spot-list" aria-label="局面">
          {items.map((it, k) => (
            <div key={it.i}>
              {(k === 0 || items[k - 1].group !== it.group) && <div className="group">{it.group}</div>}
              <button
                type="button"
                className="spot"
                aria-current={it.i === spotIndex}
                onClick={() => setSpotIndex(it.i)}
              >
                <b>{it.s.actor}</b> · {it.story}
                <small>出现概率 {(it.s.reach * 100).toFixed(1)}%</small>
              </button>
            </div>
          ))}
        </nav>
      </div>

      <section style={{ display: "grid", gap: 14, minWidth: 0 }}>
        <div className="view-head">
          <div>
            <h2>{spot ? `${spot.actor} · ${describe(spot).story}` : "读取中"}</h2>
            {data && (
              <p className="note">
                {data.custom ? "自定义范围" : `迭代 ${data.table.iterations} 轮`} · 任一位置最多还能多赢{" "}
                {data.table.max_gain_per_100.toFixed(2)} bb/100
              </p>
            )}
          </div>
          <div className="controls">
            <input
              id="range-import"
              ref={fileInput}
              type="file"
              accept="application/json,.json"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) importFile(f);
                e.target.value = "";
              }}
            />
            <button type="button" className="ghost" onClick={() => fileInput.current?.click()}>
              导入 {size} 人范围
            </button>
            {data?.custom && (
              <button
                type="button"
                className="ghost"
                onClick={() => {
                  saveCustom(size, null);
                  setVersion((v) => v + 1);
                }}
              >
                恢复默认
              </button>
            )}
          </div>
        </div>
        {error && <p className="err">{error}</p>}
        {spot && data && <SpotGrid data={data} spot={spot} onDetail={setDetail} />}
        <div className="detail">{detail}</div>
        <p className="note">
          每个格子按动作频率分色，变淡的格子表示这手牌几乎不会走到这个局面。翻后价值用简化模型估算，和商业求解器的结果会有差别。导入的文件需要是求解器导出的同一格式，会覆盖默认范围，对局里的对手也会改用它。
        </p>
      </section>
    </div>
  );
}

function SpotGrid({ data, spot, onDetail }: { data: IndexedTable; spot: Spot; onDetail: (s: string) => void }) {
  const totals = spot.actions.map(() => 0);
  let mass = 0;
  data.table.hands.forEach((h, i) => {
    const [w, ...f] = spot.hands[i];
    const c = combos(h) * w;
    mass += c;
    f.forEach((x, k) => (totals[k] += c * x));
  });

  const cells = [];
  for (let r = 0; r < 13; r++) {
    for (let c = 0; c < 13; c++) {
      const name = r === c ? RANKS[r] + RANKS[c] : r < c ? RANKS[r] + RANKS[c] + "s" : RANKS[c] + RANKS[r] + "o";
      const [w, ...f] = spot.hands[data.handIndex.get(name)!];
      const show = () =>
        onDetail(
          `${name}：` +
            spot.actions.map((a, k) => `${a} ${(f[k] * 100).toFixed(0)}%`).join(" · ") +
            (w < 0.02 ? "（几乎不在范围内）" : ""),
        );
      cells.push(
        <div
          key={name}
          className={`cell${w < 0.02 ? " out" : ""}`}
          tabIndex={0}
          onMouseEnter={show}
          onFocus={show}
          onClick={show}
        >
          {f.map((x, k) => (
            <div
              key={k}
              className="segm"
              style={{ width: `${(x * 100).toFixed(1)}%`, background: actionColor(spot.actions[k], spot.actions) }}
            />
          ))}
          <span className="name">{name}</span>
        </div>,
      );
    }
  }

  return (
    <>
      <div className="legend">
        {spot.actions.map((a, k) => (
          <span key={a}>
            <i style={{ background: actionColor(a, spot.actions) }} />
            {a} <em>{mass ? ((totals[k] / mass) * 100).toFixed(1) : "0.0"}%</em>
          </span>
        ))}
      </div>
      <div className="grid13" role="img" aria-label="13×13 起手牌策略">
        {cells}
      </div>
    </>
  );
}
