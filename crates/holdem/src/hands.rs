use crate::cards::{rank, rank_char, suit, Card};

/// 不区分花色时的起手牌种类数：13 种对子、78 种同花、78 种不同花。
pub const NUM_CLASSES: usize = 169;
/// 两张牌的组合总数 C(52, 2)。
pub const TOTAL_COMBOS: usize = 1326;

/// 169 种起手牌之一，按常见的 13×13 方格编号：
/// 行和列都从 A（0）排到 2（12），对角线是对子，右上是同花，左下是不同花。
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub struct HandClass(pub u8);

impl HandClass {
    pub fn all() -> impl Iterator<Item = HandClass> {
        (0..NUM_CLASSES as u8).map(HandClass)
    }

    pub fn index(self) -> usize {
        self.0 as usize
    }

    fn row_col(self) -> (u8, u8) {
        (self.0 / 13, self.0 % 13)
    }

    pub fn is_pair(self) -> bool {
        let (r, c) = self.row_col();
        r == c
    }

    pub fn is_suited(self) -> bool {
        let (r, c) = self.row_col();
        r < c
    }

    /// 高牌和低牌的点数（0 是 2，12 是 A）。
    pub fn ranks(self) -> (u8, u8) {
        let (r, c) = self.row_col();
        let (hi, lo) = (r.min(c), r.max(c));
        (12 - hi, 12 - lo)
    }

    pub fn num_combos(self) -> usize {
        if self.is_pair() {
            6
        } else if self.is_suited() {
            4
        } else {
            12
        }
    }

    pub fn combos(self) -> Vec<[Card; 2]> {
        let (hi, lo) = self.ranks();
        let mut out = Vec::with_capacity(self.num_combos());
        for s1 in 0..4u8 {
            for s2 in 0..4u8 {
                let keep = if self.is_pair() {
                    s1 < s2
                } else if self.is_suited() {
                    s1 == s2
                } else {
                    s1 != s2
                };
                if keep {
                    out.push([hi * 4 + s1, lo * 4 + s2]);
                }
            }
        }
        out
    }

    pub fn of_cards(a: Card, b: Card) -> HandClass {
        let (hi, lo) = if rank(a) >= rank(b) { (a, b) } else { (b, a) };
        let (row_hi, row_lo) = (12 - rank(hi), 12 - rank(lo));
        let idx = if row_hi == row_lo || suit(hi) == suit(lo) {
            row_hi * 13 + row_lo
        } else {
            row_lo * 13 + row_hi
        };
        HandClass(idx)
    }

    /// "AA"、"AKs"、"T9o" 这样的写法。
    pub fn name(self) -> String {
        let (hi, lo) = self.ranks();
        let mut s = format!("{}{}", rank_char(hi), rank_char(lo));
        if !self.is_pair() {
            s.push(if self.is_suited() { 's' } else { 'o' });
        }
        s
    }

    pub fn from_name(name: &str) -> Option<HandClass> {
        HandClass::all().find(|h| h.name().eq_ignore_ascii_case(name))
    }
}
