import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { setPostflopSolver } from "./gto/coach";
import { inDesktop, tauriSolver } from "./gto/tauri";
import "./styles.css";

// 桌面应用里，翻后两人底池交给后端求解器。
if (inDesktop) setPostflopSolver(tauriSolver);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
