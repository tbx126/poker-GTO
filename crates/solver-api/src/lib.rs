//! 桌面应用调用的求解接口，不依赖 Tauri，外壳只需把这里的函数包成命令。
//!
//! - 翻前：读取 `<人数>max.bin` 范围表。
//! - 翻后两人底池：每条街开始时用走到这里的双方范围在后台重新求解，
//!   求解过程中回报进度；求完后给出任一节点上某个座位实际手牌的各动作频率和 EV。
//!
//! 只支持从翻牌开始就是两人的底池，多人底池由前端用规则近似。

mod engine;
mod line;
mod types;

pub use engine::{Engine, EngineOptions};
pub use types::{ActionAdvice, HandState, MoveKind, PostflopMove, Progress, SolverStrategy};
