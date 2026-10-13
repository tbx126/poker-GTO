use std::collections::VecDeque;

/// 翻前求解的参数。金额单位都是大盲（bb）。
#[derive(Clone, Debug)]
pub struct Config {
    pub players: usize,
    pub stack: f32,
    pub small_blind: f32,
    pub big_blind: f32,
    /// 首个加注（开池）到多少。
    pub open: f32,
    /// 3bet 到“当前注额 × 倍数 + 每个跟注者 × 当前注额”，按 3bet 者翻后是否有位置区分。
    pub three_bet_ip: f32,
    pub three_bet_oop: f32,
    /// 4bet 到“当前注额 × 倍数”。
    pub four_bet_ip: f32,
    pub four_bet_oop: f32,
}

impl Config {
    pub fn new(players: usize) -> Config {
        assert!((2..=6).contains(&players), "只支持 2 到 6 人");
        Config {
            players,
            stack: 100.0,
            small_blind: 0.5,
            big_blind: 1.0,
            open: 2.5,
            three_bet_ip: 3.0,
            three_bet_oop: 4.0,
            four_bet_ip: 2.25,
            four_bet_oop: 2.5,
        }
    }

    /// 翻前行动顺序中第 `seat` 个座位的名称（最后两个是小盲和大盲）。
    pub fn position_name(&self, seat: usize) -> &'static str {
        const NAMES: [&str; 6] = ["UTG", "HJ", "CO", "BTN", "SB", "BB"];
        if self.players == 2 {
            return ["SB", "BB"][seat];
        }
        NAMES[6 - self.players + seat]
    }

    /// 翻后行动顺序：数值越大越晚行动，最大的是最有位置的玩家。
    pub fn postflop_order(&self, seat: usize) -> usize {
        let n = self.players;
        if n == 2 {
            // 单挑时小盲就是按钮，翻后最后行动。
            return 1 - seat;
        }
        if seat == n - 2 {
            0
        } else if seat == n - 1 {
            1
        } else {
            seat + 2
        }
    }
}

#[derive(Clone, Copy, PartialEq, Debug)]
pub enum Action {
    Fold,
    Call,
    /// 加注到这个总额。
    Raise(f32),
    AllIn,
}

pub enum Node {
    Decision {
        player: usize,
        actions: Vec<Action>,
        children: Vec<usize>,
        /// 在策略数组里的起始位置，这个节点占 169 × 动作数 个格子。
        offset: usize,
    },
    Terminal {
        /// 每个座位投入底池的金额。
        contrib: Vec<f32>,
        /// 没有弃牌的座位，按座位号排序。
        alive: Vec<usize>,
        /// 剩下的玩家都已全下，直接按胜率摊牌，不再有翻后行动。
        allin: bool,
    },
}

/// 翻前下注树，节点 0 是根。
pub struct Tree {
    pub config: Config,
    pub nodes: Vec<Node>,
    /// 所有决策节点合计的 169 × 动作数。
    pub strategy_len: usize,
}

#[derive(Clone)]
struct State {
    contrib: Vec<f32>,
    folded: Vec<bool>,
    allin: Vec<bool>,
    bet: f32,
    /// 0 未开池，1 已开池，2 已 3bet，3 已 4bet，4 有人全下。
    level: u8,
    last_raiser: Option<usize>,
    callers: usize,
    pending: VecDeque<usize>,
}

impl Tree {
    pub fn build(config: Config) -> Tree {
        let n = config.players;
        let mut contrib = vec![0.0; n];
        contrib[n - 2] = config.small_blind;
        contrib[n - 1] = config.big_blind;
        let root = State {
            contrib,
            folded: vec![false; n],
            allin: vec![false; n],
            bet: config.big_blind,
            level: 0,
            last_raiser: None,
            callers: 0,
            pending: (0..n).collect(),
        };
        let mut tree = Tree {
            config,
            nodes: Vec::new(),
            strategy_len: 0,
        };
        tree.expand(root);
        tree
    }

    pub fn root(&self) -> usize {
        0
    }

    /// 沿着一串动作走到的节点。
    pub fn follow(&self, path: &[Action]) -> Option<usize> {
        let mut node = self.root();
        for action in path {
            let Node::Decision {
                actions, children, ..
            } = &self.nodes[node]
            else {
                return None;
            };
            node = children[actions.iter().position(|a| a == action)?];
        }
        Some(node)
    }

    pub fn num_decisions(&self) -> usize {
        self.nodes
            .iter()
            .filter(|n| matches!(n, Node::Decision { .. }))
            .count()
    }

    fn legal(&self, s: &State, player: usize) -> Vec<Action> {
        let c = &self.config;
        let ip = |p: usize, other: Option<usize>| {
            other.is_none_or(|o| c.postflop_order(p) > c.postflop_order(o))
        };
        let raise = match s.level {
            0 => Some(c.open),
            1 => {
                let mult = if ip(player, s.last_raiser) {
                    c.three_bet_ip
                } else {
                    c.three_bet_oop
                };
                Some(mult * s.bet + s.callers as f32 * s.bet)
            }
            2 => {
                let mult = if ip(player, s.last_raiser) {
                    c.four_bet_ip
                } else {
                    c.four_bet_oop
                };
                Some(mult * s.bet)
            }
            _ => None,
        };
        let mut actions = vec![Action::Fold];
        if s.level > 0 {
            actions.push(Action::Call);
        }
        match raise {
            Some(to) if to < c.stack => actions.push(Action::Raise(to)),
            Some(_) => actions.push(Action::AllIn),
            None => {}
        }
        // 面对 3bet 和 4bet 时额外提供全下。
        if (2..=3).contains(&s.level) && !actions.contains(&Action::AllIn) {
            actions.push(Action::AllIn);
        }
        actions
    }

    fn apply(&self, s: &State, player: usize, action: Action) -> State {
        let stack = self.config.stack;
        let mut next = s.clone();
        next.pending.pop_front();
        let raise_to = match action {
            Action::Fold => {
                next.folded[player] = true;
                None
            }
            Action::Call => {
                next.contrib[player] = s.bet.min(stack);
                next.allin[player] = next.contrib[player] >= stack;
                next.callers += 1;
                None
            }
            Action::Raise(to) => Some(to),
            Action::AllIn => Some(stack),
        };
        if let Some(to) = raise_to {
            let n = self.config.players;
            next.contrib[player] = to;
            next.bet = to;
            next.allin[player] = to >= stack;
            next.level = if to >= stack { 4 } else { s.level + 1 };
            next.last_raiser = Some(player);
            next.callers = 0;
            next.pending = (1..n)
                .map(|i| (player + i) % n)
                .filter(|&q| !next.folded[q] && !next.allin[q])
                .collect();
        }
        next
    }

    fn expand(&mut self, s: State) -> usize {
        let id = self.nodes.len();
        let alive: Vec<usize> = (0..self.config.players).filter(|&p| !s.folded[p]).collect();
        if alive.len() == 1 || s.pending.is_empty() {
            let allin = alive.len() > 1 && alive.iter().any(|&p| s.allin[p]);
            self.nodes.push(Node::Terminal {
                contrib: s.contrib,
                alive,
                allin,
            });
            return id;
        }
        let player = s.pending[0];
        let actions = self.legal(&s, player);
        let offset = self.strategy_len;
        self.strategy_len += holdem::NUM_CLASSES * actions.len();
        self.nodes.push(Node::Decision {
            player,
            actions: actions.clone(),
            children: Vec::new(),
            offset,
        });
        let children: Vec<usize> = actions
            .iter()
            .map(|&a| {
                let next = self.apply(&s, player, a);
                self.expand(next)
            })
            .collect();
        if let Node::Decision { children: c, .. } = &mut self.nodes[id] {
            *c = children;
        }
        id
    }
}
