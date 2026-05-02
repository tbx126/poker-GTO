/** Top-of-panel header — title/subtitle plus whichever stats are available. */

import type { ScenarioStrategy } from "./mockData";

export function PanelHeader({ s }: { s: ScenarioStrategy }) {
  return (
    <div className="panel-header">
      <div>
        <div className="panel-title">{s.title}</div>
        <div className="panel-subtitle">{s.subtitle}</div>
      </div>
      <div className="panel-stats">
        {s.equity !== undefined && (
          <div className="stat">
            <span className="stat-label">Equity</span>
            <span className="stat-value">{(s.equity * 100).toFixed(1)}%</span>
          </div>
        )}
        {s.ev !== undefined && (
          <div className="stat">
            <span className="stat-label">EV</span>
            <span className={`stat-value ${s.ev > 0 ? "ev-pos" : s.ev < 0 ? "ev-neg" : ""}`}>
              {s.ev >= 0 ? "+" : ""}{s.ev.toFixed(2)} bb
            </span>
          </div>
        )}
        {s.vpip !== undefined && (
          <div className="stat">
            <span className="stat-label">VPIP</span>
            <span className="stat-value">{(s.vpip * 100).toFixed(1)}%</span>
          </div>
        )}
      </div>
    </div>
  );
}
