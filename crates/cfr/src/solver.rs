use crate::tree::{Node, Tree};

/// 每个信息集上的动作概率，按信息集编号索引。
#[derive(Clone, Debug)]
pub struct Strategy {
    pub probs: Vec<Vec<f64>>,
}

impl Strategy {
    pub fn uniform(tree: &Tree) -> Strategy {
        let probs = tree
            .infosets
            .iter()
            .map(|info| vec![1.0 / info.num_actions as f64; info.num_actions])
            .collect();
        Strategy { probs }
    }
}

/// CFR+：遗憾值截断到非负、交替更新、平均策略按迭代轮次线性加权。
pub struct Solver<'a> {
    tree: &'a Tree,
    regrets: Vec<Vec<f64>>,
    regret_delta: Vec<Vec<f64>>,
    strategy_sum: Vec<Vec<f64>>,
    iteration: usize,
}

impl<'a> Solver<'a> {
    pub fn new(tree: &'a Tree) -> Self {
        let zeros: Vec<Vec<f64>> = tree
            .infosets
            .iter()
            .map(|info| vec![0.0; info.num_actions])
            .collect();
        Solver {
            tree,
            regrets: zeros.clone(),
            regret_delta: zeros.clone(),
            strategy_sum: zeros,
            iteration: 0,
        }
    }

    pub fn iterations(&self) -> usize {
        self.iteration
    }

    pub fn run(&mut self, iterations: usize) {
        for _ in 0..iterations {
            self.iteration += 1;
            for player in 0..2 {
                self.traverse(self.tree.root(), player, 1.0, 1.0);
                // 一个信息集可能对应多条历史，这一轮的遗憾全部累加完再截断。
                for (regrets, delta) in self.regrets.iter_mut().zip(&mut self.regret_delta) {
                    for (r, d) in regrets.iter_mut().zip(delta.iter_mut()) {
                        *r = (*r + *d).max(0.0);
                        *d = 0.0;
                    }
                }
            }
        }
    }

    /// 迄今为止的平均策略，也就是收敛到均衡的那一个。
    pub fn average_strategy(&self) -> Strategy {
        let probs = self.strategy_sum.iter().map(|sum| normalize(sum)).collect();
        Strategy { probs }
    }

    /// 返回 `player` 在该节点的期望收益。`reach_self` 是 `player` 自己的到达概率，
    /// `reach_others` 是对手和机会节点的到达概率之积。
    fn traverse(&mut self, node: usize, player: usize, reach_self: f64, reach_others: f64) -> f64 {
        match &self.tree.nodes[node] {
            Node::Terminal { payoff } => sign(player) * payoff,
            Node::Chance { children } => children
                .iter()
                .map(|&(child, p)| p * self.traverse(child, player, reach_self, reach_others * p))
                .sum(),
            Node::Decision {
                player: actor,
                infoset,
                children,
            } => {
                let (actor, infoset) = (*actor, *infoset);
                let sigma = normalize(&self.regrets[infoset]);
                if actor != player {
                    return children
                        .iter()
                        .zip(&sigma)
                        .map(|(&child, &s)| {
                            s * self.traverse(child, player, reach_self, reach_others * s)
                        })
                        .sum();
                }
                let values: Vec<f64> = children
                    .iter()
                    .zip(&sigma)
                    .map(|(&child, &s)| self.traverse(child, player, reach_self * s, reach_others))
                    .collect();
                let value: f64 = values.iter().zip(&sigma).map(|(v, s)| v * s).sum();
                let weight = self.iteration as f64 * reach_self;
                for a in 0..values.len() {
                    self.regret_delta[infoset][a] += reach_others * (values[a] - value);
                    self.strategy_sum[infoset][a] += weight * sigma[a];
                }
                value
            }
        }
    }
}

/// 可剥削度：两名玩家各自用最佳应对能多赢的平均值，单位与收益相同。
/// 达到纳什均衡时为 0。
pub fn exploitability(tree: &Tree, strategy: &Strategy) -> f64 {
    (best_response_value(tree, strategy, 0) + best_response_value(tree, strategy, 1)) / 2.0
}

/// `player` 针对对手的 `strategy` 采取最佳应对时的期望收益。
fn best_response_value(tree: &Tree, strategy: &Strategy, player: usize) -> f64 {
    // 每个信息集里的历史，以及到达该历史的对手与机会概率之积。
    let mut members: Vec<Vec<(usize, f64)>> = vec![Vec::new(); tree.infosets.len()];
    collect_members(tree, strategy, player, tree.root(), 1.0, &mut members);
    let mut br = BestResponse {
        tree,
        strategy,
        player,
        members,
        choice: vec![None; tree.infosets.len()],
        value: vec![None; tree.nodes.len()],
    };
    br.node_value(tree.root())
}

fn collect_members(
    tree: &Tree,
    strategy: &Strategy,
    player: usize,
    node: usize,
    reach: f64,
    members: &mut [Vec<(usize, f64)>],
) {
    match &tree.nodes[node] {
        Node::Terminal { .. } => {}
        Node::Chance { children } => {
            for &(child, p) in children {
                collect_members(tree, strategy, player, child, reach * p, members);
            }
        }
        Node::Decision {
            player: actor,
            infoset,
            children,
        } => {
            if *actor == player {
                members[*infoset].push((node, reach));
                for &child in children {
                    collect_members(tree, strategy, player, child, reach, members);
                }
            } else {
                for (&child, &s) in children.iter().zip(&strategy.probs[*infoset]) {
                    collect_members(tree, strategy, player, child, reach * s, members);
                }
            }
        }
    }
}

struct BestResponse<'a> {
    tree: &'a Tree,
    strategy: &'a Strategy,
    player: usize,
    members: Vec<Vec<(usize, f64)>>,
    choice: Vec<Option<usize>>,
    value: Vec<Option<f64>>,
}

impl BestResponse<'_> {
    fn node_value(&mut self, node: usize) -> f64 {
        if let Some(v) = self.value[node] {
            return v;
        }
        let v = match &self.tree.nodes[node] {
            Node::Terminal { payoff } => sign(self.player) * payoff,
            Node::Chance { children } => children
                .iter()
                .map(|&(child, p)| p * self.node_value(child))
                .sum(),
            Node::Decision {
                player: actor,
                infoset,
                children,
            } => {
                if *actor == self.player {
                    let a = self.choose(*infoset);
                    self.node_value(children[a])
                } else {
                    children
                        .iter()
                        .zip(&self.strategy.probs[*infoset])
                        .map(|(&child, &s)| s * self.node_value(child))
                        .sum()
                }
            }
        };
        self.value[node] = Some(v);
        v
    }

    /// 信息集上的最佳动作：按到达权重汇总该信息集内所有历史的收益后取最大。
    fn choose(&mut self, infoset: usize) -> usize {
        if let Some(a) = self.choice[infoset] {
            return a;
        }
        let num_actions = self.tree.infosets[infoset].num_actions;
        let mut totals = vec![0.0; num_actions];
        for (node, weight) in self.members[infoset].clone() {
            let Node::Decision { children, .. } = &self.tree.nodes[node] else {
                unreachable!()
            };
            for (a, &child) in children.clone().iter().enumerate() {
                totals[a] += weight * self.node_value(child);
            }
        }
        let best = (0..num_actions)
            .max_by(|&x, &y| totals[x].total_cmp(&totals[y]))
            .expect("决策节点至少有一个动作");
        self.choice[infoset] = Some(best);
        best
    }
}

fn sign(player: usize) -> f64 {
    if player == 0 {
        1.0
    } else {
        -1.0
    }
}

/// 遗憾匹配：按正值比例分配；全部为零时取均匀分布。
fn normalize(values: &[f64]) -> Vec<f64> {
    let total: f64 = values.iter().map(|v| v.max(0.0)).sum();
    if total > 0.0 {
        values.iter().map(|v| v.max(0.0) / total).collect()
    } else {
        vec![1.0 / values.len() as f64; values.len()]
    }
}

/// 双方都按 `strategy` 行动时玩家 0 的期望收益。
pub fn expected_value(tree: &Tree, strategy: &Strategy) -> f64 {
    fn walk(tree: &Tree, strategy: &Strategy, node: usize) -> f64 {
        match &tree.nodes[node] {
            Node::Terminal { payoff } => *payoff,
            Node::Chance { children } => children
                .iter()
                .map(|&(child, p)| p * walk(tree, strategy, child))
                .sum(),
            Node::Decision {
                infoset, children, ..
            } => children
                .iter()
                .zip(&strategy.probs[*infoset])
                .map(|(&child, &s)| s * walk(tree, strategy, child))
                .sum(),
        }
    }
    walk(tree, strategy, tree.root())
}
