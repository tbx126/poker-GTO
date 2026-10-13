use std::collections::HashMap;

/// 博弈中某个状态的类型。
pub enum GameNode {
    /// 终局，数值是玩家 0 的收益（玩家 1 的收益为其相反数）。
    Terminal(f64),
    /// 机会节点，每个元素是对应结果的概率。
    Chance(Vec<f64>),
    /// 决策节点。
    Decision { player: usize, num_actions: usize },
}

/// 两人零和、完美回忆博弈的规则描述。
pub trait Game {
    type State: Clone;

    fn root(&self) -> Self::State;
    fn node(&self, state: &Self::State) -> GameNode;
    /// 执行第 `index` 个动作（机会节点上是第 `index` 个结果）。
    fn apply(&self, state: &Self::State, index: usize) -> Self::State;
    /// 当前行动玩家的信息集标识，只能包含该玩家可见的信息。
    fn infoset_key(&self, state: &Self::State) -> String;
}

pub enum Node {
    Terminal {
        payoff: f64,
    },
    Chance {
        children: Vec<(usize, f64)>,
    },
    Decision {
        player: usize,
        infoset: usize,
        children: Vec<usize>,
    },
}

pub struct InfosetInfo {
    pub player: usize,
    pub num_actions: usize,
    pub key: String,
}

/// 展开后的显式博弈树，节点 0 是根。
pub struct Tree {
    pub nodes: Vec<Node>,
    pub infosets: Vec<InfosetInfo>,
}

impl Tree {
    pub fn build<G: Game>(game: &G) -> Tree {
        let mut tree = Tree {
            nodes: Vec::new(),
            infosets: Vec::new(),
        };
        let mut index = HashMap::new();
        tree.expand(game, &game.root(), &mut index);
        tree
    }

    pub fn root(&self) -> usize {
        0
    }

    pub fn infoset_id(&self, key: &str) -> Option<usize> {
        self.infosets.iter().position(|info| info.key == key)
    }

    fn expand<G: Game>(
        &mut self,
        game: &G,
        state: &G::State,
        index: &mut HashMap<String, usize>,
    ) -> usize {
        let id = self.nodes.len();
        // 先占位，保证父节点编号小于子节点。
        self.nodes.push(Node::Terminal { payoff: 0.0 });
        let node = match game.node(state) {
            GameNode::Terminal(payoff) => Node::Terminal { payoff },
            GameNode::Chance(probs) => {
                let children = probs
                    .iter()
                    .enumerate()
                    .map(|(i, &p)| (self.expand(game, &game.apply(state, i), index), p))
                    .collect();
                Node::Chance { children }
            }
            GameNode::Decision {
                player,
                num_actions,
            } => {
                let key = format!("{player}|{}", game.infoset_key(state));
                let infoset = *index.entry(key.clone()).or_insert_with(|| {
                    self.infosets.push(InfosetInfo {
                        player,
                        num_actions,
                        key,
                    });
                    self.infosets.len() - 1
                });
                assert_eq!(
                    self.infosets[infoset].num_actions, num_actions,
                    "同一信息集内的动作数必须相同"
                );
                let children = (0..num_actions)
                    .map(|a| self.expand(game, &game.apply(state, a), index))
                    .collect();
                Node::Decision {
                    player,
                    infoset,
                    children,
                }
            }
        };
        self.nodes[id] = node;
        id
    }
}
