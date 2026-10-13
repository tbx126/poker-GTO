use crate::tree::{Action, Node, Tree};
use holdem::NUM_CLASSES as N;

/// 一条翻前行动线走完后的结果：每个座位的范围和底池情况，用来接翻后求解。
pub struct Line {
    /// 每个座位每类起手牌走完这条线的概率（不含起手牌本身的出现概率）。
    pub ranges: Vec<Vec<f64>>,
    /// 每个座位投入底池的金额，单位 bb。
    pub contrib: Vec<f32>,
    /// 没有弃牌的座位，按座位号排序。
    pub alive: Vec<usize>,
    /// 走到的节点。线还没结束时是决策节点。
    pub node: usize,
}

/// 沿着一串翻前动作，把每一步行动者的策略乘进他的范围。
pub fn follow_line(tree: &Tree, strategy: &[f64], path: &[Action]) -> Option<Line> {
    let n = tree.config.players;
    let mut ranges = vec![vec![1.0; N]; n];
    let mut node = tree.root();
    for action in path {
        let Node::Decision {
            player,
            actions,
            children,
            offset,
        } = &tree.nodes[node]
        else {
            return None;
        };
        let k = actions.iter().position(|a| a == action)?;
        let a = actions.len();
        for (h, w) in ranges[*player].iter_mut().enumerate() {
            *w *= strategy[offset + h * a + k];
        }
        node = children[k];
    }
    let (contrib, alive) = match &tree.nodes[node] {
        Node::Terminal { contrib, alive, .. } => (contrib.clone(), alive.clone()),
        Node::Decision { .. } => (Vec::new(), Vec::new()),
    };
    Some(Line {
        ranges,
        contrib,
        alive,
        node,
    })
}
