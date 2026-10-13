//! 两人零和、完美回忆博弈的表格型 CFR+ 求解器。
//!
//! 流程：先用 [`Game`] 描述规则，再用 [`Tree::build`] 展开成显式博弈树，
//! 然后交给 [`Solver`] 迭代，最后用 [`exploitability`] 衡量策略离均衡有多远。
//!
//! 这一层只服务于小规模博弈（库恩扑克、Leduc）和算法正确性验证；
//! 德州扑克的翻前和翻后求解器有各自针对性的实现。

pub mod games;
mod solver;
mod tree;

pub use solver::{expected_value, exploitability, Solver, Strategy};
pub use tree::{Game, GameNode, Node, Tree};
