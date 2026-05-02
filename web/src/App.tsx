import { useState } from "react";
import { ACTIONS } from "./actions";
import type { HandStrategy } from "./actions";
import type { PreflopLock, TreeConfig } from "./api";
import { DEFAULT_TREE, solvePreflop } from "./api";
import { PanelHeader } from "./PanelHeader";
import { RangeHeatmap } from "./RangeHeatmap";
import { StrategyDetail } from "./StrategyDetail";
import { SolverConsole } from "./SolverConsole";
import { ScenarioConfig } from "./ScenarioConfig";
import { SCENARIO_BTN_VS_BB } from "./mockData";
import type { ScenarioStrategy } from "./mockData";
import { responseToScenarios } from "./preflopAdapter";
import "./App.css";

interface Selection {
  hand: string;
  strategy: HandStrategy;
}

interface Scenario {
  oop: ScenarioStrategy;
  ip: ScenarioStrategy;
  source: "mock" | "live";
  meta?: { iters: number; exploitability: number; elapsed_ms: number };
}

type SideLocks = Record<string, number[]>;

const INITIAL_SCENARIO: Scenario = {
  oop: SCENARIO_BTN_VS_BB.oop,
  ip: SCENARIO_BTN_VS_BB.ip,
  source: "mock",
};

const DEFAULT_PREFLOP_ITERS = 80;

function buildLockPayload(scenario: Scenario, locks: { oop: SideLocks; ip: SideLocks }): PreflopLock[] {
  const out: PreflopLock[] = [];
  if (scenario.oop.meta) {
    for (const [hand, probs] of Object.entries(locks.oop)) {
      out.push({ history: scenario.oop.meta.history, hand, probs });
    }
  }
  if (scenario.ip.meta) {
    for (const [hand, probs] of Object.entries(locks.ip)) {
      out.push({ history: scenario.ip.meta.history, hand, probs });
    }
  }
  return out;
}

export function App() {
  const [oopSel, setOopSel] = useState<Selection | null>(null);
  const [ipSel, setIpSel] = useState<Selection | null>(null);
  const [consoleOpen, setConsoleOpen] = useState(false);
  const [scenario, setScenario] = useState<Scenario>(INITIAL_SCENARIO);
  const [solving, setSolving] = useState(false);
  const [solveErr, setSolveErr] = useState<string | null>(null);
  const [locks, setLocks] = useState<{ oop: SideLocks; ip: SideLocks }>({ oop: {}, ip: {} });
  const [cfg, setCfg] = useState<TreeConfig>(DEFAULT_TREE);
  const [cfgOpen, setCfgOpen] = useState(false);

  async function runPreflopSolve() {
    setSolving(true);
    setSolveErr(null);
    try {
      const r = await solvePreflop(DEFAULT_PREFLOP_ITERS, buildLockPayload(scenario, locks), cfg);
      const next = responseToScenarios(r);
      setScenario({
        oop: next.oop,
        ip: next.ip,
        source: "live",
        meta: {
          iters: r.iters,
          exploitability: r.final_exploitability,
          elapsed_ms: r.elapsed_ms,
        },
      });
      setOopSel(null);
      setIpSel(null);
    } catch (e) {
      setSolveErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSolving(false);
    }
  }

  function resetToMock() {
    setScenario(INITIAL_SCENARIO);
    setOopSel(null);
    setIpSel(null);
    setLocks({ oop: {}, ip: {} });
  }

  function setLock(side: "oop" | "ip", hand: string, probs: number[]) {
    setLocks((prev) => ({ ...prev, [side]: { ...prev[side], [hand]: probs } }));
  }

  function clearLock(side: "oop" | "ip", hand: string) {
    setLocks((prev) => {
      const sideLocks = { ...prev[side] };
      delete sideLocks[hand];
      return { ...prev, [side]: sideLocks };
    });
  }

  function clearAllLocks() {
    setLocks({ oop: {}, ip: {} });
  }

  const { oop, ip } = scenario;
  const totalLocks = Object.keys(locks.oop).length + Object.keys(locks.ip).length;
  const oopLockSet = new Set(Object.keys(locks.oop));
  const ipLockSet = new Set(Object.keys(locks.ip));

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">Poker GTO</div>
        <button className="scenario-pill scenario-btn" onClick={() => setCfgOpen(true)}>
          {`HU · ${cfg.stack}bb · 开 ${cfg.open_to}x · 3bet ${cfg.threebet_to}`} ⚙
        </button>
        <span className={`source-badge ${scenario.source}`}>
          {scenario.source === "live" ? "实时求解" : "示例数据"}
        </span>
        {scenario.meta && (
          <span className="solve-meta">
            {scenario.meta.iters} iter · ε={scenario.meta.exploitability.toExponential(2)} ·{" "}
            {scenario.meta.elapsed_ms}ms
          </span>
        )}
        {totalLocks > 0 && (
          <span className="lock-pill">
            🔒 {totalLocks} 处锁定
            <button className="link-btn" onClick={clearAllLocks}>
              清空
            </button>
          </span>
        )}
        <div className="actions">
          <button disabled>群体倾向</button>
          {scenario.source === "live" && (
            <button onClick={resetToMock} disabled={solving}>
              恢复示例
            </button>
          )}
          <button onClick={() => setConsoleOpen(true)}>玩具博弈</button>
          <button className="primary" onClick={runPreflopSolve} disabled={solving}>
            {solving ? "求解中…" : totalLocks > 0 ? `带锁求解 (${totalLocks})` : "求解翻前"}
          </button>
        </div>
      </header>

      {solveErr && (
        <div className="banner-error">
          求解失败：{solveErr}（确认后端 uvicorn 是否在 8090 上运行）
        </div>
      )}

      <SolverConsole open={consoleOpen} onClose={() => setConsoleOpen(false)} />
      <ScenarioConfig
        open={cfgOpen}
        initial={cfg}
        onClose={() => setCfgOpen(false)}
        onSave={(next) => {
          setCfg(next);
          setCfgOpen(false);
        }}
      />

      <main className="panels">
        <section className="panel">
          <PanelHeader s={oop} />
          <RangeHeatmap
            strategy={oop.strategy}
            lockedHands={oopLockSet}
            selected={oopSel?.hand ?? null}
            onSelect={(hand, strategy) => setOopSel({ hand, strategy })}
          />
          <StrategyDetail
            hand={oopSel?.hand ?? null}
            strategy={oopSel?.strategy ?? null}
            meta={oop.meta}
            currentLock={oopSel ? locks.oop[oopSel.hand] : undefined}
            onLock={(probs) => oopSel && setLock("oop", oopSel.hand, probs)}
            onUnlock={() => oopSel && clearLock("oop", oopSel.hand)}
          />
        </section>

        <section className="panel">
          <PanelHeader s={ip} />
          <RangeHeatmap
            strategy={ip.strategy}
            lockedHands={ipLockSet}
            selected={ipSel?.hand ?? null}
            onSelect={(hand, strategy) => setIpSel({ hand, strategy })}
          />
          <StrategyDetail
            hand={ipSel?.hand ?? null}
            strategy={ipSel?.strategy ?? null}
            meta={ip.meta}
            currentLock={ipSel ? locks.ip[ipSel.hand] : undefined}
            onLock={(probs) => ipSel && setLock("ip", ipSel.hand, probs)}
            onUnlock={() => ipSel && clearLock("ip", ipSel.hand)}
          />
        </section>
      </main>

      <footer className="legend">
        {ACTIONS.map((a) => (
          <div key={a.key} className="legend-item">
            <span className="dot" style={{ background: a.color }} />
            {a.label}
          </div>
        ))}
      </footer>
    </div>
  );
}
