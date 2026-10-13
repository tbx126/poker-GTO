use crate::tree::{Game, GameNode};

/// Leduc 扑克：六张牌（J、Q、K 各两张），每人底注 1，每人一张手牌。
/// 两轮下注，第一轮下注额 2，翻出一张公共牌后第二轮下注额 4，每轮最多加注两次。
/// 摊牌时和公共牌成对者胜，否则比手牌大小。先手玩家的均衡收益约为 -0.0856。
pub struct Leduc;

#[derive(Clone, Copy, PartialEq, Debug)]
enum Action {
    Fold,
    Call,
    Raise,
}

#[derive(Clone)]
pub struct LeducState {
    private: Option<[u8; 2]>,
    public: Option<u8>,
    /// 每轮的动作序列，第二轮开始前为空。
    rounds: Vec<Vec<Action>>,
    contributions: [f64; 2],
    folded: Option<usize>,
}

impl LeducState {
    fn round(&self) -> &[Action] {
        self.rounds.last().map(Vec::as_slice).unwrap_or(&[])
    }

    fn to_act(&self) -> usize {
        self.round().len() % 2
    }

    fn facing_bet(&self) -> bool {
        self.contributions[0] != self.contributions[1]
    }

    fn raises(&self) -> usize {
        self.round().iter().filter(|&&a| a == Action::Raise).count()
    }

    fn round_closed(&self) -> bool {
        let r = self.round();
        // 过牌-过牌，或者有人跟注了下注。
        r.len() >= 2 && r.last() == Some(&Action::Call)
    }

    fn legal(&self) -> Vec<Action> {
        let mut actions = Vec::with_capacity(3);
        if self.facing_bet() {
            actions.push(Action::Fold);
        }
        actions.push(Action::Call);
        if self.raises() < 2 {
            actions.push(Action::Raise);
        }
        actions
    }
}

fn rank(card: u8) -> u8 {
    card / 2
}

/// 两张不同手牌的所有有序组合。
fn deals() -> Vec<[u8; 2]> {
    (0..6)
        .flat_map(|a| (0..6).filter(move |&b| b != a).map(move |b| [a, b]))
        .collect()
}

impl Leduc {
    fn remaining(s: &LeducState) -> Vec<u8> {
        let private = s.private.expect("已发手牌");
        (0..6).filter(|c| !private.contains(c)).collect()
    }
}

impl Game for Leduc {
    type State = LeducState;

    fn root(&self) -> LeducState {
        LeducState {
            private: None,
            public: None,
            rounds: vec![Vec::new()],
            contributions: [1.0, 1.0],
            folded: None,
        }
    }

    fn node(&self, s: &LeducState) -> GameNode {
        let Some(private) = s.private else {
            return GameNode::Chance(vec![1.0 / 30.0; 30]);
        };
        if let Some(p) = s.folded {
            return GameNode::Terminal(if p == 0 {
                -s.contributions[0]
            } else {
                s.contributions[1]
            });
        }
        if s.round_closed() {
            match s.public {
                None => return GameNode::Chance(vec![0.25; 4]),
                Some(public) => {
                    let strength = |c: u8| {
                        if rank(c) == rank(public) {
                            10 + rank(c)
                        } else {
                            rank(c)
                        }
                    };
                    let (a, b) = (strength(private[0]), strength(private[1]));
                    let stake = s.contributions[0];
                    return GameNode::Terminal(match a.cmp(&b) {
                        std::cmp::Ordering::Greater => stake,
                        std::cmp::Ordering::Less => -stake,
                        std::cmp::Ordering::Equal => 0.0,
                    });
                }
            }
        }
        GameNode::Decision {
            player: s.to_act(),
            num_actions: s.legal().len(),
        }
    }

    fn apply(&self, s: &LeducState, index: usize) -> LeducState {
        let mut next = s.clone();
        if s.private.is_none() {
            next.private = Some(deals()[index]);
            return next;
        }
        if s.round_closed() {
            next.public = Some(Leduc::remaining(s)[index]);
            next.rounds.push(Vec::new());
            return next;
        }
        let player = s.to_act();
        let action = s.legal()[index];
        let bet = if s.public.is_none() { 2.0 } else { 4.0 };
        match action {
            Action::Fold => next.folded = Some(player),
            Action::Call => next.contributions[player] = s.contributions[1 - player],
            Action::Raise => next.contributions[player] = s.contributions[1 - player] + bet,
        }
        next.rounds.last_mut().expect("至少有一轮").push(action);
        next
    }

    fn infoset_key(&self, s: &LeducState) -> String {
        let private = s.private.expect("决策前已发牌");
        let me = s.to_act();
        let public = s.public.map(rank);
        format!("{}:{:?}:{:?}", rank(private[me]), public, s.rounds)
    }
}
