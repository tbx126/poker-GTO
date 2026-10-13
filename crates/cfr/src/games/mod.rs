//! 已知精确解的小规模扑克，用来验证求解器本身是否正确。

mod kuhn;
mod leduc;

pub use kuhn::Kuhn;
pub use leduc::Leduc;
