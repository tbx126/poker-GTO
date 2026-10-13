//! 两人底池的翻后精确求解。
//!
//! 输入公共牌、双方范围、底池和有效筹码，按精确模式的下注尺寸建树，
//! 交给 `postflop-solver`（Discounted CFR，多线程）求解，直到可剥削度低于底池的给定比例。
//! 筹码统一用 0.01bb 作单位，和翻前求解器的 bb 互相换算。

mod range;
mod sizes;
mod solve;

pub use range::{range_from_classes, range_from_combos};
pub use sizes::{Sizes, StreetSizes};
pub use solve::{
    build_game, build_game_unallocated, next_street_spot, solve, Outcome, Progress, SolveOptions,
    Spot,
};

/// 每 bb 合多少个求解器筹码。
pub const CHIPS_PER_BB: f32 = 100.0;

/// bb 换成求解器筹码，四舍五入。
pub fn to_chips(bb: f32) -> i32 {
    (bb * CHIPS_PER_BB).round() as i32
}

/// 求解器筹码换回 bb。
pub fn to_bb(chips: f32) -> f32 {
    chips / CHIPS_PER_BB
}
