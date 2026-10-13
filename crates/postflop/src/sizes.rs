use postflop_solver::{BetSizeOptions, DonkSizeOptions};

/// 一条街的下注尺寸，写法沿用 postflop-solver：
/// 下注 "33%, 75%" 表示底池的 33% 和 75%，加注 "3x" 表示对手下注额的 3 倍，"a" 表示全下。
#[derive(Clone, Debug)]
pub struct StreetSizes {
    pub bet: String,
    pub raise: String,
}

impl StreetSizes {
    fn new(bet: &str, raise: &str) -> StreetSizes {
        StreetSizes {
            bet: bet.to_string(),
            raise: raise.to_string(),
        }
    }

    pub fn options(&self) -> Result<BetSizeOptions, String> {
        BetSizeOptions::try_from((self.bet.as_str(), self.raise.as_str()))
    }
}

/// 三条街的下注尺寸，双方相同。
#[derive(Clone, Debug)]
pub struct Sizes {
    pub flop: StreetSizes,
    pub turn: StreetSizes,
    pub river: StreetSizes,
    /// 没位置的一方在上一条街跟注后领先下注的尺寸；空串表示不允许领先下注。
    pub donk: String,
    /// 最大下注不超过底池的这个倍数时，额外加一个全下选项。
    pub add_allin_threshold: f64,
    /// 对手跟注后剩余筹码与底池之比不超过这个值时，强制改成全下。
    pub force_allin_threshold: f64,
    /// 尺寸太接近时合并，规则和 PioSOLVER 相同。
    pub merging_threshold: f64,
}

impl Sizes {
    /// 精确模式，按要求解的那条街取尺寸。`board_len` 是当前公共牌张数（3、4 或 5）。
    ///
    /// 每条街都会用当时的范围重新求解，所以只有当前这条街用完整尺寸，
    /// 后面的街只保留一个尺寸，把翻牌的树控制在几个 GB 以内。
    /// 完整尺寸：翻牌 33%、75%；转牌 50%、100%；河牌 33%、75%、150%；加注都是 3 倍，另有全下。
    pub fn precise(board_len: usize) -> Sizes {
        let (flop, turn, river) = match board_len {
            3 => (("33%, 75%", "3x"), ("75%", "3x"), ("75%", "")),
            4 => (("75%", "3x"), ("50%, 100%", "3x"), ("33%, 75%, 150%", "3x")),
            _ => (("75%", "3x"), ("75%", "3x"), ("33%, 75%, 150%", "3x")),
        };
        Sizes {
            flop: StreetSizes::new(flop.0, flop.1),
            turn: StreetSizes::new(turn.0, turn.1),
            river: StreetSizes::new(river.0, river.1),
            donk: String::new(),
            add_allin_threshold: 1.5,
            force_allin_threshold: 0.15,
            merging_threshold: 0.1,
        }
    }

    pub(crate) fn donk_options(&self) -> Result<Option<DonkSizeOptions>, String> {
        let donk = if self.donk.trim().is_empty() {
            DonkSizeOptions { donk: Vec::new() }
        } else {
            DonkSizeOptions::try_from(self.donk.as_str())?
        };
        Ok(Some(donk))
    }
}
