//! 2 到 6 人、100bb、无抽水的翻前求解器。
//!
//! 下注树只保留常用尺寸（开池 2.5bb、3bet、4bet、全下），翻后用 [`Model`] 近似估值，
//! 再用 CFR+ 求出各位置各起手牌的策略。这里是 CPU 参考实现，GPU 版本以它为准做对照。

mod model;
mod solver;
mod tree;

pub use model::Model;
pub use solver::{evaluate, prior, Report, Solver};
pub use tree::{Action, Config, Node, Tree};
