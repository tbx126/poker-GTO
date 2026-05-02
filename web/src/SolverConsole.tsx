/**
 * Live-solver console: select game, run CFR+ against the FastAPI service,
 * and inspect the convergence trajectory plus the converged strategy table.
 */

import { useEffect, useState } from "react";
import { type GameName, type SolveResponse, ping, solve } from "./api";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function SolverConsole({ open, onClose }: Props) {
  const [game, setGame] = useState<GameName>("kuhn");
  const [iters, setIters] = useState(2000);
  const [chunks, setChunks] = useState(8);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SolveResponse | null>(null);
  const [serverUp, setServerUp] = useState<boolean | null>(null);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    ping().then((up) => alive && setServerUp(up));
    return () => {
      alive = false;
    };
  }, [open]);

  async function run() {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const r = await solve(game, iters, chunks);
      setResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  if (!open) return null;

  return (
    <div className="console-overlay" onClick={onClose}>
      <div className="console" onClick={(e) => e.stopPropagation()}>
        <div className="console-header">
          <h3>实时 CFR+ 求解</h3>
          <button onClick={onClose}>关闭</button>
        </div>

        <div className="console-controls">
          <label>
            游戏
            <select value={game} onChange={(e) => setGame(e.target.value as GameName)}>
              <option value="kuhn">Kuhn</option>
              <option value="leduc">Leduc</option>
            </select>
          </label>
          <label>
            迭代
            <input
              type="number"
              min={1}
              max={50000}
              value={iters}
              onChange={(e) => setIters(Number(e.target.value))}
            />
          </label>
          <label>
            采样点
            <input
              type="number"
              min={1}
              max={50}
              value={chunks}
              onChange={(e) => setChunks(Number(e.target.value))}
            />
          </label>
          <button className="primary" disabled={running || serverUp === false} onClick={run}>
            {running ? "求解中…" : "运行"}
          </button>
          <span className={`server-state ${serverUp === false ? "down" : "up"}`}>
            {serverUp === null ? "检测后端…" : serverUp ? "后端在线" : "后端离线 (启动 uvicorn)"}
          </span>
        </div>

        {error && <div className="console-error">错误：{error}</div>}

        {result && (
          <div className="console-results">
            <div className="result-summary">
              <span>
                <strong>{result.iters}</strong> 次迭代
              </span>
              <span>
                最终可剥削度 <strong>{result.final_exploitability.toExponential(3)}</strong>
              </span>
              <span>
                耗时 <strong>{result.elapsed_ms}</strong> ms
              </span>
            </div>

            <ConvergenceChart trajectory={result.trajectory} />

            <div className="strategy-table">
              <div className="strategy-header">
                <span>infoset</span>
                <span>动作分布</span>
              </div>
              {result.strategies.map((s) => (
                <div key={s.infoset} className="strategy-row">
                  <span className="iso-key">{s.infoset}</span>
                  <span className="iso-probs">
                    {s.actions.map((a, i) => (
                      <span key={a} className="iso-action">
                        <em>{a}</em> {(s.probs[i] * 100).toFixed(1)}%
                      </span>
                    ))}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ConvergenceChart({ trajectory }: { trajectory: { iter: number; exploitability: number }[] }) {
  if (!trajectory.length) return null;
  const W = 480;
  const H = 120;
  const PAD = 24;
  const xs = trajectory.map((p) => p.iter);
  const ys = trajectory.map((p) => Math.max(p.exploitability, 1e-12));
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yLogs = ys.map((y) => Math.log10(y));
  const yMin = Math.min(...yLogs);
  const yMax = Math.max(...yLogs);
  const xRange = Math.max(xMax - xMin, 1);
  const yRange = Math.max(yMax - yMin, 0.5);

  const pts = trajectory.map((p, i) => {
    const x = PAD + ((p.iter - xMin) / xRange) * (W - 2 * PAD);
    const y = PAD + (1 - (yLogs[i] - yMin) / yRange) * (H - 2 * PAD);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  return (
    <svg className="conv-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="convergence">
      <rect x={0} y={0} width={W} height={H} fill="#0e1015" />
      <text x={PAD} y={14} fill="#8a93a6" fontSize={10}>
        log10 exploitability vs iters
      </text>
      <polyline
        fill="none"
        stroke="#f1d76e"
        strokeWidth={1.5}
        points={pts.join(" ")}
      />
      {pts.map((p, i) => {
        const [x, y] = p.split(",").map(Number);
        return <circle key={i} cx={x} cy={y} r={2.5} fill="#f1d76e" />;
      })}
    </svg>
  );
}
