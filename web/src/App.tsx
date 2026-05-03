import { useState, useEffect, useCallback, useMemo } from "react";
import { ACTIONS, type ActionKey, type HandStrategy as BarStrategy } from "./actions";
import type { HandStrategy as ApiHandStrategy, PreflopScenarioRequest, PreflopStrategyResponse } from "./api";
import { getPreflopStrategyMatrix } from "./api";
import { RangeHeatmap } from "./RangeHeatmap";
import "./App.css";

/** Reduce API per-action arrays into a per-color-bucket map for the heatmap bars. */
function apiToBars(apiStrat: ApiHandStrategy): BarStrategy {
  const out: BarStrategy = {};
  for (let i = 0; i < apiStrat.actions.length; i++) {
    const kind = apiStrat.action_kinds[i] as ActionKey;
    const prob = apiStrat.probs[i] ?? 0;
    if (prob <= 0) continue;
    out[kind] = (out[kind] ?? 0) + prob;
  }
  return out;
}

// Positions for 6-max
const POSITIONS = ["UTG", "HJ", "CO", "BTN", "SB", "BB"] as const;
type Position = typeof POSITIONS[number];

// Scenario types
type ScenarioType = "open" | "face_open" | "face_3bet" | "face_4bet";

interface ActionRecord {
  position: Position;
  action: string;
  size?: number;
}

export function App() {
  // Scenario state
  const [heroPosition, setHeroPosition] = useState<Position>("BTN");
  const [scenarioType, setScenarioType] = useState<ScenarioType>("open");
  const [effectiveStack, setEffectiveStack] = useState(100);
  const [tableSize] = useState(6);

  // Action history
  const [actionHistory, setActionHistory] = useState<ActionRecord[]>([]);
  const [raiserPosition, setRaiserPosition] = useState<Position | null>(null);
  const [threeBettor, setThreeBettor] = useState<Position | null>(null);

  // Strategy data
  const [strategyData, setStrategyData] = useState<PreflopStrategyResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Selected hand for detail view
  const [selectedHand, setSelectedHand] = useState<string | null>(null);

  // Fetch strategy matrix when scenario changes
  const fetchStrategy = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const req: PreflopScenarioRequest = {
        table_size: tableSize,
        effective_stack: effectiveStack,
        hero_position: heroPosition,
        scenario_type: scenarioType,
      };

      if (scenarioType === "face_open" && raiserPosition) {
        req.raiser_position = raiserPosition;
        req.raise_size = 2.5;
      }

      if (scenarioType === "face_3bet" && raiserPosition && threeBettor) {
        req.raiser_position = raiserPosition;
        req.raise_size = 2.5;
        req.three_bettor = threeBettor;
        req.three_bet_size = 9.0;
      }

      const data = await getPreflopStrategyMatrix(req);
      setStrategyData(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [tableSize, effectiveStack, heroPosition, scenarioType, raiserPosition, threeBettor]);

  useEffect(() => {
    fetchStrategy();
  }, [fetchStrategy]);

  // Reset selected positions when hero or scenario changes
  useEffect(() => {
    setRaiserPosition(null);
    setThreeBettor(null);
  }, [scenarioType, heroPosition]);

  // Auto-populate action history from scenario state
  useEffect(() => {
    const history: ActionRecord[] = [];
    if ((scenarioType === "face_open" || scenarioType === "face_3bet") && raiserPosition) {
      history.push({ position: raiserPosition, action: "开池加注", size: 2.5 });
    }
    if (scenarioType === "face_3bet" && raiserPosition && threeBettor) {
      history.push({ position: threeBettor, action: "3-bet", size: 9 });
    }
    if (scenarioType === "face_4bet") {
      // Generic representation; UI does not yet expose 4-bettor position.
      history.push({ position: heroPosition, action: "开池加注", size: 2.5 });
      history.push({ position: "BB", action: "3-bet", size: 9 });
      history.push({ position: heroPosition, action: "4-bet", size: 22 });
    }
    setActionHistory(history);
  }, [scenarioType, heroPosition, raiserPosition, threeBettor]);

  // Convert API strategies to bar shape once per fetch
  const heatmapStrategy = useMemo<Record<string, BarStrategy>>(() => {
    if (!strategyData) return {};
    const out: Record<string, BarStrategy> = {};
    for (const [hand, apiStrat] of Object.entries(strategyData.strategies)) {
      out[hand] = apiToBars(apiStrat);
    }
    return out;
  }, [strategyData]);

  const getSelectedHandStrategy = (): ApiHandStrategy | null => {
    if (!selectedHand || !strategyData) return null;
    return strategyData.strategies[selectedHand] || null;
  };

  // Get scenario description
  const getScenarioDescription = (): string => {
    if (!strategyData) return "";
    return strategyData.scenario_description;
  };

  const SCENARIO_OPTIONS: { key: ScenarioType; label: string }[] = [
    { key: "open", label: "开池" },
    { key: "face_open", label: "面对开池" },
    { key: "face_3bet", label: "面对 3-bet" },
    { key: "face_4bet", label: "面对 4-bet" },
  ];

  const STACK_PRESETS = [20, 50, 100, 200];

  const renderActionHistory = () => {
    if (actionHistory.length === 0) {
      return <div className="history-empty">尚无对手行动</div>;
    }
    return (
      <div className="history-list">
        {actionHistory.map((record, i) => (
          <div key={i} className="history-row">
            <span className="history-pos">{record.position}</span>
            <span className="history-act">{record.action}</span>
            {record.size != null && <span className="history-size">{record.size}bb</span>}
          </div>
        ))}
      </div>
    );
  };

  const renderPositionGrid = (
    selected: Position | null,
    onPick: (p: Position) => void,
    disabled?: (p: Position) => boolean,
  ) => (
    <div className="position-grid">
      {POSITIONS.map((pos) => {
        const isDisabled = disabled?.(pos) ?? false;
        return (
          <button
            key={pos}
            className={`btn compact ${selected === pos ? "active" : ""}`}
            onClick={() => !isDisabled && onPick(pos)}
            aria-disabled={isDisabled}
          >
            {pos}
          </button>
        );
      })}
    </div>
  );

  const renderScenarioControls = () => (
    <>
      <div className="section">
        <div className="section-label">你的位置</div>
        {renderPositionGrid(heroPosition, (p) => setHeroPosition(p))}
      </div>

      <div className="section">
        <div className="section-label">场景类型</div>
        <div className="scenario-grid">
          {SCENARIO_OPTIONS.map((opt) => (
            <button
              key={opt.key}
              className={`btn ${scenarioType === opt.key ? "active" : ""}`}
              onClick={() => setScenarioType(opt.key)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {(scenarioType === "face_open" || scenarioType === "face_3bet") && (
        <div className="section">
          <div className="section-label">开池位置</div>
          {renderPositionGrid(
            raiserPosition,
            (p) => setRaiserPosition(p),
            (p) => p === heroPosition,
          )}
        </div>
      )}

      {scenarioType === "face_3bet" && (
        <div className="section">
          <div className="section-label">3-bet 位置</div>
          {renderPositionGrid(
            threeBettor,
            (p) => setThreeBettor(p),
            (p) => p === heroPosition || p === raiserPosition,
          )}
        </div>
      )}

      <div className="section">
        <div className="section-label">有效筹码</div>
        <div className="stack-control">
          <div className="stack-readout">
            <div>
              <span className="stack-value">{effectiveStack}</span>
              <span className="stack-unit"> bb</span>
            </div>
            <input
              className="stack-num"
              type="number"
              min={10}
              max={500}
              value={effectiveStack}
              onChange={(e) => setEffectiveStack(Number(e.target.value) || 0)}
            />
          </div>
          <input
            className="slider"
            type="range"
            min={10}
            max={300}
            step={5}
            value={Math.min(effectiveStack, 300)}
            onChange={(e) => setEffectiveStack(Number(e.target.value))}
          />
          <div className="stack-presets">
            {STACK_PRESETS.map((v) => (
              <button
                key={v}
                className={`stack-preset ${effectiveStack === v ? "active" : ""}`}
                onClick={() => setEffectiveStack(v)}
              >
                {v}bb
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="section">
        <div className="section-label">行动顺序</div>
        {renderActionHistory()}
      </div>
    </>
  );

  const renderStrategyDetail = () => {
    const handStrategy = getSelectedHandStrategy();
    if (!handStrategy) {
      return (
        <div className="detail-empty">
          点击上方热力图中的任意手牌查看详细策略
        </div>
      );
    }

    const total = handStrategy.probs.reduce((s, p) => s + p, 0) || 1;
    const combos = selectedHand && selectedHand.length === 2
      ? "6 combos · 对子"
      : selectedHand?.endsWith("s")
        ? "4 combos · 同花"
        : "12 combos · 非同花";

    return (
      <div className="detail-panel">
        <div className="detail-head">
          <span className="detail-hand">{selectedHand}</span>
          <span className="detail-meta">{combos}</span>
        </div>
        <div className="detail-actions">
          {handStrategy.actions.map((action, i) => {
            const prob = handStrategy.probs[i];
            const pct = (prob / total) * 100;
            if (pct < 0.5) return null;

            const kind = handStrategy.action_kinds[i] as ActionKey;
            const actionMeta = ACTIONS.find((a) => a.key === kind);
            const color = actionMeta?.color || "#666";
            const label = actionMeta?.label || action;

            return (
              <div key={action} className="detail-row">
                <span className="dot" style={{ background: color }} />
                <span className="action-name">{label}</span>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${pct}%`, background: color }} />
                </div>
                <span className="pct">{pct.toFixed(1)}%</span>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  // Pot estimation for table visualization
  const potBB = (() => {
    if (scenarioType === "open") return 1.5; // sb + bb
    if (scenarioType === "face_open") return 4; // 2.5 + 1 + 0.5
    if (scenarioType === "face_3bet") return 12.5; // 9 + 2.5 + 1 (rough)
    if (scenarioType === "face_4bet") return 31.5;
    return 1.5;
  })();

  const heroIdx = POSITIONS.indexOf(heroPosition);
  const btnIdx = POSITIONS.indexOf("BTN");
  const seatRadius = 130;

  const getSeatTransform = (positionIndex: number) => {
    const offset = ((positionIndex - heroIdx) + tableSize) % tableSize;
    const angle = (offset * 360) / tableSize + 90;
    return `translate(-50%, -50%) rotate(${angle}deg) translateY(-${seatRadius}px) rotate(-${angle}deg)`;
  };

  const getDealerButtonStyle = (): React.CSSProperties => {
    const offset = ((btnIdx - heroIdx) + tableSize) % tableSize;
    const angle = (offset * 360) / tableSize + 90;
    const rad = (angle - 90) * (Math.PI / 180); // -90° because CSS rotates from top
    const r = seatRadius - 56; // closer to felt edge
    const x = Math.cos(rad) * r;
    const y = Math.sin(rad) * r;
    return {
      left: `calc(50% + ${x}px - 9px)`,
      top: `calc(50% + ${y}px - 9px)`,
    };
  };

  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <div className="brand">
          <span className="brand-name">Poker GTO</span>
          <span className="brand-tag">preflop trainer</span>
        </div>
        <div className="header-info">
          {strategyData && (
            <>
              <span className="scenario-pill">{getScenarioDescription()}</span>
              <span className="stat-strip">
                <span className="stat-cell">
                  <span className="stat-dot" style={{ background: "var(--check-call)" }} />
                  <span className="stat-key">VPIP</span>
                  <span className="stat-val">{(strategyData.vpip * 100).toFixed(1)}%</span>
                </span>
                <span className="stat-cell">
                  <span className="stat-dot" style={{ background: "var(--bet-100)" }} />
                  <span className="stat-key">Raise</span>
                  <span className="stat-val">{(strategyData.raise_freq * 100).toFixed(1)}%</span>
                </span>
                {strategyData.call_freq > 0 && (
                  <span className="stat-cell">
                    <span className="stat-dot" style={{ background: "var(--accent)" }} />
                    <span className="stat-key">Call</span>
                    <span className="stat-val">{(strategyData.call_freq * 100).toFixed(1)}%</span>
                  </span>
                )}
              </span>
            </>
          )}
        </div>
        <div className="header-status">
          {loading && <span className="spinner" aria-label="加载中" />}
          {error && <span className="error-indicator">{error}</span>}
        </div>
      </header>

      {/* Main Content */}
      <main className="main-content">
        {/* Left Side - Heatmap */}
        <section className="left-panel">
          <div className="panel-header">
            <div className="panel-title">
              手牌策略热力图
              <span className="panel-sub">169 hand classes</span>
            </div>
            <div className="legend">
              {ACTIONS.map((a) => (
                <div key={a.key} className="legend-item">
                  <span className="dot" style={{ background: a.color }} />
                  {a.label}
                </div>
              ))}
            </div>
          </div>
          <div className="heatmap-container">
            <RangeHeatmap
              strategy={heatmapStrategy}
              onSelect={(hand) => setSelectedHand(hand)}
              selected={selectedHand}
            />
          </div>
          {renderStrategyDetail()}
        </section>

        {/* Right Side - Table & Controls */}
        <section className="right-panel">
          <div className="panel-header">
            <div className="panel-title">
              牌局实况
              <span className="panel-sub">{tableSize}-max</span>
            </div>
          </div>

          <div className="right-scroll">
            {/* Table */}
            <div className="table-scene">
              <div className="poker-table">
                <div className="table-felt" />
                <div className="pot-area">
                  <div className="pot-label">Pot</div>
                  <div className="pot-value">{potBB}bb</div>
                </div>
                <div className="seats">
                  {POSITIONS.slice(0, tableSize).map((pos, i) => {
                    const isHero = pos === heroPosition;
                    const isRaiser = pos === raiserPosition;
                    const isThreeBettor = pos === threeBettor;

                    let actionLabel: string | null = null;
                    let actionClass = "";
                    if (isThreeBettor) {
                      actionLabel = "3-bet";
                      actionClass = "act-3bet";
                    } else if (isRaiser) {
                      actionLabel = "Raise";
                      actionClass = "act-raise";
                    } else if (isHero) {
                      actionLabel = "Hero";
                      actionClass = "act-hero";
                    }

                    return (
                      <div
                        key={pos}
                        className={[
                          "seat",
                          isHero ? "hero" : "",
                          isRaiser ? "raiser" : "",
                          isThreeBettor ? "three-bettor" : "",
                        ].filter(Boolean).join(" ")}
                        style={{ transform: getSeatTransform(i) }}
                      >
                        <div className="seat-position">{pos}</div>
                        <div className="seat-stack">{effectiveStack}bb</div>
                        {isHero && <div className="seat-cards">🂠 🂠</div>}
                        {actionLabel && (
                          <div className={`seat-action ${actionClass}`}>{actionLabel}</div>
                        )}
                      </div>
                    );
                  })}
                </div>
                <div className="dealer-button" style={getDealerButtonStyle()}>D</div>
              </div>
            </div>

            {/* Scenario Controls */}
            {renderScenarioControls()}
          </div>
        </section>
      </main>
    </div>
  );
}
