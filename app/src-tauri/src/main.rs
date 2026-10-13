// Windows 发布版不弹出控制台窗口。
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use solver_api::{ApproxStrategy, Engine, EngineOptions, HandState, LegalMove, SolverStrategy};
use tauri::{AppHandle, Emitter, Manager, State};

/// 当前局面能否交给求解器（翻牌开始就是两人底池，而且找得到对应人数的翻前范围表）。
#[tauri::command]
fn solver_supports(engine: State<'_, Engine>, state: HandState) -> bool {
    engine.supports(&state)
}

/// 开始这条街的后台求解，进度通过 `solver-progress` 事件发给前端。
#[tauri::command]
fn solver_prepare(
    app: AppHandle,
    engine: State<'_, Engine>,
    state: HandState,
) -> Result<(), String> {
    engine.prepare(&state, move |p| {
        let _ = app.emit("solver-progress", p);
    })
}

/// 等这条街求解完，返回 `seat` 在当前节点的策略。求解可能要几十秒，放到阻塞线程池里等。
#[tauri::command]
async fn solver_strategy(
    engine: State<'_, Engine>,
    state: HandState,
    seat: usize,
) -> Result<SolverStrategy, String> {
    let engine = engine.inner().clone();
    tauri::async_runtime::spawn_blocking(move || engine.strategy(&state, seat))
        .await
        .map_err(|e| e.to_string())?
}

/// 一手牌结束或换桌时取消后台求解，释放内存。
#[tauri::command]
async fn solver_approx(
    engine: State<'_, Engine>,
    state: HandState,
    seat: usize,
    legal: Vec<LegalMove>,
) -> Result<ApproxStrategy, String> {
    let engine = engine.inner().clone();
    tauri::async_runtime::spawn_blocking(move || engine.approx(&state, seat, &legal))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
fn solver_cancel(engine: State<'_, Engine>, hand_id: String) {
    engine.cancel(&hand_id);
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            // 安装包里带着仓库 data/preflop/ 下的完整翻前策略。
            let dir = app.path().resource_dir()?.join("preflop");
            app.manage(Engine::new(&dir, EngineOptions::default()));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            solver_supports,
            solver_prepare,
            solver_strategy,
            solver_approx,
            solver_cancel
        ])
        .run(tauri::generate_context!())
        .expect("启动应用失败");
}
