//! 德州扑克基础：牌的表示、七张牌型评估、169 种起手牌，以及两人全下胜率表。

mod cards;
mod equity;
mod eval;
mod hands;

pub use cards::{card_name, parse_card, Card, Deck};
pub use equity::{EquityTable, Rng};
pub use eval::{evaluate, HandRank};
pub use hands::{HandClass, NUM_CLASSES, TOTAL_COMBOS};
