/// 一张牌，取值 0 到 51：点数 = 值 / 4（0 是 2，12 是 A），花色 = 值 % 4。
pub type Card = u8;

const RANKS: &[u8; 13] = b"23456789TJQKA";
const SUITS: &[u8; 4] = b"cdhs";

pub fn rank(card: Card) -> u8 {
    card / 4
}

pub fn suit(card: Card) -> u8 {
    card % 4
}

pub fn card_name(card: Card) -> String {
    format!(
        "{}{}",
        RANKS[rank(card) as usize] as char,
        SUITS[suit(card) as usize] as char
    )
}

/// 解析 "As"、"Td" 这样的写法。
pub fn parse_card(s: &str) -> Option<Card> {
    let b = s.as_bytes();
    if b.len() != 2 {
        return None;
    }
    let r = RANKS.iter().position(|&c| c == b[0].to_ascii_uppercase())?;
    let s = SUITS.iter().position(|&c| c == b[1].to_ascii_lowercase())?;
    Some((r * 4 + s) as Card)
}

/// 用 64 位掩码记录已用的牌。
#[derive(Clone, Copy, Default)]
pub struct Deck {
    used: u64,
}

impl Deck {
    pub fn contains(&self, card: Card) -> bool {
        self.used & (1 << card) != 0
    }

    pub fn take(&mut self, card: Card) {
        self.used |= 1 << card;
    }
}

pub(crate) fn rank_char(r: u8) -> char {
    RANKS[r as usize] as char
}
