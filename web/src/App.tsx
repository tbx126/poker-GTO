import { useState, useEffect, useCallback } from "react";
import { ACTIONS, type ActionKey, type HandStrategy } from "./actions";
import type { PreflopScenarioRequest, PreflopStrategyResponse } from "./api";
import { getPreflopStrategyMatrix } from "./api";
import { RangeHeatmap } from "./RangeHeatmap";
import "./App.css";

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
  const [tableSize, setTableSize] = useState(6);

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

  // Reset action history when scenario changes
  useEffect(() => {
    setActionHistory([]);
    setRaiserPosition(null);
    setThreeBettor(null);
  }, [scenarioType, heroPosition]);

  // Get strategy for heatmap
  const getHeatmapStrategy = (): Record<string, HandStrategy> => {
    if (!strategyData) return {};
    return strategyData.strategies;
  };

  // Get selected hand strategy
  const getSelectedHandStrategy = (): HandStrategy | null => {
    if (!selectedHand || !strategyData) return null;
    return strategyData.strategies[selectedHand] || null;
  };

  // Get scenario description
  const getScenarioDescription = (): string => {
    if (!strategyData) return "";
    return strategyData.scenario_description;
  };

  // Render action history
  const renderActionHistory = () => {
    if (actionHistory.length === 0) {
      return <div className="history-empty">无操作记录</div>;
    }

    return actionHistory.map((record, i) => (
      <div key={i} className="history-item">
        <span className="history-position">{record.position}</span>
        <span className="history-action">{record.action}</span>
        {record.size && <span className="history-size">{record.size}bb</span>}
      </div>
    ));
  };

  // Render scenario controls
  const renderScenarioControls = () => {
    return (
      <div className="scenario-controls">
        {/* Hero Position */}
        <div className="control-group">
          <label>你的位置</label>
          <div className="position-buttons">
            {POSITIONS.map((pos) => (
              <button
                key={pos}
                className={`pos-btn ${heroPosition === pos ? "active" : ""}`}
                onClick={() => setHeroPosition(pos)}
              >
                {pos}
              </button>
            ))}
          </div>
        </div>

        {/* Scenario Type */}
        <div className="control-group">
          <label>场景类型</label>
          <div className="scenario-buttons">
            <button
              className={`scenario-btn ${scenarioType === "open" ? "active" : ""}`}
              onClick={() => setScenarioType("open")}
            >
              开池
            </button>
            <button
              className={`scenario-btn ${scenarioType === "face_open" ? "active" : ""}`}
              onClick={() => setScenarioType("face_open")}
            >
              面对开池
            </button>
            <button
              className={`scenario-btn ${scenarioType === "face_3bet" ? "active" : ""}`}
              onClick={() => setScenarioType("face_3bet")}
            >
              面对3-bet
            </button>
            <button
              className={`scenario-btn ${scenarioType === "face_4bet" ? "active" : ""}`}
              onClick={() => setScenarioType("face_4bet")}
            >
              面对4-bet
            </button>
          </div>
        </div>

        {/* Raiser Position (for face_open/face_3bet) */}
        {(scenarioType === "face_open" || scenarioType === "face_3bet") && (
          <div className="control-group">
            <label>开池位置</label>
            <div className="position-buttons">
              {POSITIONS.filter((p) => p !== heroPosition).map((pos) => (
                <button
                  key={pos}
                  className={`pos-btn ${raiserPosition === pos ? "active" : ""}`}
                  onClick={() => setRaiserPosition(pos)}
                >
                  {pos}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* 3-bettor Position (for face_3bet) */}
        {scenarioType === "face_3bet" && (
          <div className="control-group">
            <label>3-bet位置</label>
            <div className="position-buttons">
              {POSITIONS.filter((p) => p !== heroPosition && p !== raiserPosition).map((pos) => (
                <button
                  key={pos}
                  className={`pos-btn ${threeBettor === pos ? "active" : ""}`}
                  onClick={() => setThreeBettor(pos)}
                >
                  {pos}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Stack Size */}
        <div className="control-group">
          <label>筹码深度 (BB)</label>
          <div className="stack-input">
            <input
              type="number"
              min={10}
              max={500}
              value={effectiveStack}
              onChange={(e) => setEffectiveStack(Number(e.target.value))}
            />
            <div className="stack-presets">
              <button onClick={() => setEffectiveStack(20)}>20bb</button>
              <button onClick={() => setEffectiveStack(50)}>50bb</button>
              <button onClick={() => setEffectiveStack(100)}>100bb</button>
              <button onClick={() => setEffectiveStack(200)}>200bb</button>
            </div>
          </div>
        </div>
      </div>
    );
  };

  // Render strategy detail
  const renderStrategyDetail = () => {
    const handStrategy = getSelectedHandStrategy();
    if (!handStrategy) {
      return (
        <div className="detail-empty">
          点击热力图中的手牌查看详细策略
        </div>
      );
    }

    const total = handStrategy.probs.reduce((s, p) => s + p, 0) || 1;

    return (
      <div className="detail-panel">
        <div className="detail-hand">{selectedHand}</div>
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

  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <div className="brand">Poker GTO</div>
        <div className="header-info">
          {strategyData && (
            <>
              <span className="scenario-badge">
                {getScenarioDescription()}
              </span>
              <span className="stat-badge">
                VPIP: {(strategyData.vpip * 100).toFixed(1)}%
              </span>
              <span className="stat-badge">
                Raise: {(strategyData.raise_freq * 100).toFixed(1)}%
              </span>
              {strategyData.call_freq > 0 && (
                <span className="stat-badge">
                  Call: {(strategyData.call_freq * 100).toFixed(1)}%
                </span>
              )}
            </>
          )}
        </div>
        {loading && <span className="loading-indicator">加载中...</span>}
        {error && <span className="error-indicator">{error}</span>}
      </header>

      {/* Main Content - Left/Right Split */}
      <main className="main-content">
        {/* Left Side - Heatmap */}
        <section className="left-panel">
          <div className="panel-header">
            <h3>手牌策略热力图</h3>
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
              strategy={getHeatmapStrategy()}
              onSelect={(hand) => setSelectedHand(hand)}
              selected={selectedHand}
            />
          </div>
          {renderStrategyDetail()}
        </section>

        {/* Right Side - Table Scene */}
        <section className="right-panel">
          <div className="panel-header">
            <h3>牌局实况</h3>
          </div>

          {/* Table Visualization */}
          <div className="table-scene">
            <div className="poker-table">
              <div className="table-center">
                <div className="pot-area">底池</div>
              </div>
              {/* Position seats */}
              <div className="seats">
                {POSITIONS.slice(0, tableSize).map((pos, i) => {
                  const angle = (i * 360) / tableSize - 90;
                  const isHero = pos === heroPosition;
                  const isRaiser = pos === raiserPosition;
                  const isThreeBettor = pos === threeBettor;

                  return (
                    <div
                      key={pos}
                      className={`seat ${isHero ? "hero" : ""} ${isRaiser ? "raiser" : ""} ${isThreeBettor ? "three-bettor" : ""}`}
                      style={{
                        transform: `rotate(${angle}deg) translateY(-140px) rotate(-${angle}deg)`,
                      }}
                    >
                      <div className="seat-position">{pos}</div>
                      <div className="seat-stack">{effectiveStack}bb</div>
                      {isHero && <div className="seat-cards">🂠🂠</div>}
                      {isRaiser && <div className="seat-action">开池</div>}
                      {isThreeBettor && <div className="seat-action">3-bet</div>}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Scenario Controls */}
          {renderScenarioControls()}

          {/* Action History */}
          <div className="action-history">
            <h4>操作记录</h4>
            {renderActionHistory()}
          </div>
        </section>
      </main>
    </div>
  );
}
