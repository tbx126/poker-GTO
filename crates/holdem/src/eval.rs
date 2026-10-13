use crate::cards::{rank, suit, Card};

/// 牌力，数值越大越强，可以直接比较。
/// 高位是牌型（0 高牌到 8 同花顺），低 20 位依次放五张决定大小的点数。
pub type HandRank = u32;

const HIGH_CARD: u32 = 0;
const PAIR: u32 = 1;
const TWO_PAIR: u32 = 2;
const TRIPS: u32 = 3;
const STRAIGHT: u32 = 4;
const FLUSH: u32 = 5;
const FULL_HOUSE: u32 = 6;
const QUADS: u32 = 7;
const STRAIGHT_FLUSH: u32 = 8;

/// 点数位掩码（第 r 位代表点数 r）中最高的顺子顶牌；没有顺子返回 None。
fn straight_high(mask: u16) -> Option<u8> {
    // 把 A 复制到最低位，用来表示 A-2-3-4-5。
    let m = ((mask as u32) << 1) | ((mask as u32 >> 12) & 1);
    (4..14)
        .rev()
        .find(|&top| (m >> (top - 4)) & 0b11111 == 0b11111)
        .map(|top| top as u8 - 1)
}

/// 从高到低取掩码中的前 `n` 个点数，依次放进 `v` 的低位。
fn push_top(mut v: u32, mask: u16, n: usize) -> u32 {
    let mut m = mask;
    for _ in 0..n {
        let r = if m == 0 { 0 } else { 15 - m.leading_zeros() };
        v = (v << 4) | r;
        m &= !(1u16 << r);
    }
    v
}

/// 牌型加上已经按顺序挑好的点数，补足到五个 4 位槽。
fn finish(category: u32, ranks: &[u32], kicker_mask: u16, kickers: usize) -> HandRank {
    let mut v = category;
    for &r in ranks {
        v = (v << 4) | r;
    }
    v = push_top(v, kicker_mask, kickers);
    v << (4 * (5 - ranks.len() - kickers))
}

/// 评估五到七张牌中最好的五张。
pub fn evaluate(cards: &[Card]) -> HandRank {
    let mut counts = [0u8; 13];
    let mut suit_masks = [0u16; 4];
    let mut rank_mask = 0u16;
    for &c in cards {
        counts[rank(c) as usize] += 1;
        suit_masks[suit(c) as usize] |= 1 << rank(c);
        rank_mask |= 1 << rank(c);
    }

    for &flush in &suit_masks {
        if flush.count_ones() >= 5 {
            if let Some(top) = straight_high(flush) {
                return finish(STRAIGHT_FLUSH, &[top as u32], 0, 0);
            }
            return finish(FLUSH, &[], flush, 5);
        }
    }

    // 从大到小找出最大的四条、两组最大的三条、两组最大的对子。
    let (mut quad, mut trip1, mut trip2, mut pair1, mut pair2) = (None, None, None, None, None);
    for r in (0..13u32).rev() {
        match counts[r as usize] {
            4 if quad.is_none() => quad = Some(r),
            3 if trip1.is_none() => trip1 = Some(r),
            3 if trip2.is_none() => trip2 = Some(r),
            2 if pair1.is_none() => pair1 = Some(r),
            2 if pair2.is_none() => pair2 = Some(r),
            _ => {}
        }
    }
    let without = |rs: &[u32]| rs.iter().fold(rank_mask, |m, &r| m & !(1u16 << r));

    if let Some(q) = quad {
        return finish(QUADS, &[q], without(&[q]), 1);
    }
    if let Some(t) = trip1 {
        // 第二组三条也可以当对子用。
        if let Some(p) = trip2.max(pair1) {
            return finish(FULL_HOUSE, &[t, p], 0, 0);
        }
    }
    if let Some(top) = straight_high(rank_mask) {
        return finish(STRAIGHT, &[top as u32], 0, 0);
    }
    if let Some(t) = trip1 {
        return finish(TRIPS, &[t], without(&[t]), 2);
    }
    if let (Some(a), Some(b)) = (pair1, pair2) {
        return finish(TWO_PAIR, &[a, b], without(&[a, b]), 1);
    }
    if let Some(p) = pair1 {
        return finish(PAIR, &[p], without(&[p]), 3);
    }
    finish(HIGH_CARD, &[], rank_mask, 5)
}
