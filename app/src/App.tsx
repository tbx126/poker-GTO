import { useCallback, useMemo, useState } from "react";
import { HandRecord, Settings, loadHistory, loadSettings, saveHistory, saveSettings } from "./store/history";
import { Play } from "./ui/Play";
import { Ranges } from "./ui/Ranges";
import { Review } from "./ui/Review";
import { fmtBB, signed } from "./ui/colors";

type View = "play" | "review" | "ranges";

const TITLES: Record<View, string> = { play: "牌桌", review: "复盘", ranges: "翻前范围" };

export function App() {
  const [view, setView] = useState<View>(() => (location.hash === "#review" ? "review" : location.hash === "#ranges" ? "ranges" : "play"));
  const [settings, setSettings] = useState<Settings>(loadSettings);
  const [history, setHistory] = useState<HandRecord[]>(loadHistory);
  const [sessionStart] = useState(() => Date.now());

  const update = (patch: Partial<Settings>) =>
    setSettings((s) => {
      const next = { ...s, ...patch };
      saveSettings(next);
      return next;
    });

  const onHandDone = useCallback((r: HandRecord) => {
    setHistory((h) => {
      // 同一手牌可能存两次（之后补上了纠错），按编号覆盖。
      const next = h.some((x) => x.id === r.id) ? h.map((x) => (x.id === r.id ? { ...r, at: x.at } : x)) : [...h, r];
      saveHistory(next);
      return next;
    });
  }, []);

  const stats = useMemo(() => {
    const session = history.filter((h) => h.at >= sessionStart);
    const net = session.reduce((a, h) => a + h.net, 0);
    const grades = session.flatMap((h) => Object.values(h.feedback).map((f) => f.grade));
    const good = grades.filter((g) => g === "best" || g === "good").length;
    return {
      hands: session.length,
      net,
      bb100: session.length ? (net / session.length) * 100 : 0,
      accuracy: grades.length ? good / grades.length : null,
    };
  }, [history, sessionStart]);

  return (
    <div className={`shell${settings.fourColor ? " four-color" : ""}`}>
      <nav className="rail" aria-label="主导航">
        <div className="brand" aria-hidden="true">
          ♠
        </div>
        <NavButton id="play" view={view} setView={setView} label="牌桌" icon={<TableIcon />} />
        <NavButton id="review" view={view} setView={setView} label="复盘" icon={<ReplayIcon />} />
        <NavButton id="ranges" view={view} setView={setView} label="范围" icon={<GridIcon />} />
      </nav>
      <main className="main">
        <header className="topbar">
          <h1>{TITLES[view]}</h1>
          {view === "play" && (
            <div className="controls">
              <div className="seg" role="group" aria-label="桌型">
                {[2, 3, 4, 5, 6].map((n) => (
                  <button key={n} type="button" aria-pressed={settings.players === n} onClick={() => update({ players: n })}>
                    {n} 人
                  </button>
                ))}
              </div>
              <Toggle label="纠错" on={settings.coach} onChange={(v) => update({ coach: v })} />
              <Toggle label="行动前提示" on={settings.hints} onChange={(v) => update({ hints: v })} />
              <Toggle label="四色牌" on={settings.fourColor} onChange={(v) => update({ fourColor: v })} />
              <div className="seg" role="group" aria-label="对手速度">
                {(["slow", "normal", "fast"] as const).map((sp) => (
                  <button key={sp} type="button" aria-pressed={settings.speed === sp} onClick={() => update({ speed: sp })}>
                    {{ slow: "慢", normal: "中", fast: "快" }[sp]}
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="stats" aria-label="本次统计">
            <Stat label="本次手数" value={String(stats.hands)} />
            <Stat label="净赢 bb" value={signed(stats.net)} tone={stats.net} />
            <Stat label="bb/100" value={stats.hands ? signed(stats.bb100) : "—"} tone={stats.bb100} />
            <Stat label="决策准确率" value={stats.accuracy === null ? "—" : `${fmtBB(stats.accuracy * 100)}%`} />
          </div>
        </header>
        {view === "play" && <Play settings={settings} onHandDone={onHandDone} />}
        {view === "review" && <Review history={history} onPlay={() => setView("play")} />}
        {view === "ranges" && <Ranges initialPlayers={settings.players} />}
      </main>
    </div>
  );
}

function NavButton(props: { id: View; view: View; setView: (v: View) => void; label: string; icon: JSX.Element }) {
  return (
    <button
      type="button"
      className="nav-btn"
      aria-current={props.view === props.id ? "page" : undefined}
      onClick={() => props.setView(props.id)}
    >
      {props.icon}
      {props.label}
    </button>
  );
}

function Toggle({ label, on, onChange }: { label: string; on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button type="button" role="switch" aria-checked={on} className="toggle" onClick={() => onChange(!on)}>
      <span className="track" />
      {label}
    </button>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: number }) {
  const cls = tone === undefined || tone === 0 ? "" : tone > 0 ? "pos" : "neg";
  return (
    <div className="stat">
      <small>{label}</small>
      <b className={cls}>{value}</b>
    </div>
  );
}

const svg = { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round", strokeLinejoin: "round" } as const;

function TableIcon() {
  return (
    <svg {...svg} aria-hidden="true">
      <rect x="2.5" y="6" width="19" height="12" rx="6" />
      <rect x="6" y="9.5" width="3" height="5" rx="0.6" />
      <rect x="10.5" y="9.5" width="3" height="5" rx="0.6" />
    </svg>
  );
}
function ReplayIcon() {
  return (
    <svg {...svg} aria-hidden="true">
      <path d="M4 12a8 8 0 1 0 2.4-5.7" />
      <path d="M4 4v4h4" />
      <path d="M10 9.5v5l4-2.5z" />
    </svg>
  );
}
function GridIcon() {
  return (
    <svg {...svg} aria-hidden="true">
      <rect x="3.5" y="3.5" width="17" height="17" rx="2" />
      <path d="M3.5 9.2h17M3.5 14.8h17M9.2 3.5v17M14.8 3.5v17" />
    </svg>
  );
}
