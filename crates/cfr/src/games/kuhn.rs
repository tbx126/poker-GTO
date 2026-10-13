use crate::tree::{Game, GameNode};

/// 库恩扑克：三张牌 J、Q、K，每人底注 1，只有一轮下注，下注额 1。
/// 先手玩家的均衡收益为 -1/18。
pub struct Kuhn;

/// 动作 0 是过牌或弃牌，动作 1 是下注或跟注。
#[derive(Clone)]
pub struct KuhnState {
    cards: Option<[u8; 2]>,
    history: Vec<u8>,
}

/// 所有有序发牌组合：(玩家 0 的牌, 玩家 1 的牌)。
const DEALS: [[u8; 2]; 6] = [[0, 1], [0, 2], [1, 0], [1, 2], [2, 0], [2, 1]];

impl Game for Kuhn {
    type State = KuhnState;

    fn root(&self) -> KuhnState {
        KuhnState {
            cards: None,
            history: Vec::new(),
        }
    }

    fn node(&self, s: &KuhnState) -> GameNode {
        let Some(cards) = s.cards else {
            return GameNode::Chance(vec![1.0 / 6.0; 6]);
        };
        let showdown = |stake: f64| {
            if cards[0] > cards[1] {
                stake
            } else {
                -stake
            }
        };
        match s.history.as_slice() {
            [0, 0] => GameNode::Terminal(showdown(1.0)),
            [1, 1] | [0, 1, 1] => GameNode::Terminal(showdown(2.0)),
            [1, 0] => GameNode::Terminal(1.0),
            [0, 1, 0] => GameNode::Terminal(-1.0),
            h => GameNode::Decision {
                player: h.len() % 2,
                num_actions: 2,
            },
        }
    }

    fn apply(&self, s: &KuhnState, index: usize) -> KuhnState {
        let mut next = s.clone();
        match s.cards {
            None => next.cards = Some(DEALS[index]),
            Some(_) => next.history.push(index as u8),
        }
        next
    }

    fn infoset_key(&self, s: &KuhnState) -> String {
        let cards = s.cards.expect("决策前已发牌");
        let player = s.history.len() % 2;
        format!("{}:{:?}", cards[player], s.history)
    }
}
