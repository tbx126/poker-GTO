//! 2 到 6 人、100bb、无抽水的翻前求解器。
//!
//! 下注树只保留常用尺寸（开池 2.5bb、3bet、4bet、全下），翻后用 [`Model`] 近似估值，
//! 再用 CFR+ 求出各位置各起手牌的策略，子树之间多线程并行。

mod line;
mod model;
mod solver;
mod store;
mod tree;

pub use line::{follow_line, Line};
pub use model::{Model, Realization};
pub use solver::{action_values, evaluate, prior, Report, Solver};
pub use store::{action_label, export_spots_json, load, save, Meta};
pub use tree::{Action, Config, Node, Tree};
