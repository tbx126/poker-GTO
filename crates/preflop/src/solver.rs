use crate::model::{mat_vec, Model};
use crate::tree::{Node, Tree};
use holdem::{HandClass, NUM_CLASSES, TOTAL_COMBOS};
use rayon::prelude::*;
use std::sync::Mutex;

const N: usize = NUM_CLASSES;

/// 每种起手牌出现的先验概率（组合数 / 1326）。
pub fn prior() -> Vec<f64> {
    HandClass::all()
        .map(|h| h.num_combos() as f64 / TOTAL_COMBOS as f64)
        .collect()
}

/// 一个决策节点的累计遗憾和累计策略，布局都是 169 行 × 动作数。
#[derive(Default)]
struct NodeData {
    regrets: Vec<f64>,
    strategy_sum: Vec<f64>,
}

/// 翻前 CFR+：按起手牌向量化遍历公开下注树，子树之间用 rayon 并行。
///
/// 每次遍历只更新一名玩家的节点，而每个节点在一次遍历里只访问一次，
/// 所以每个节点的锁不会有竞争，只是为了让并行的子树安全地各写各的节点。
pub struct Solver<'a> {
    tree: &'a Tree,
    model: &'a Model,
    data: Vec<Mutex<NodeData>>,
    iteration: usize,
}

impl<'a> Solver<'a> {
    pub fn new(tree: &'a Tree, model: &'a Model) -> Self {
        let data = tree
            .nodes
            .iter()
            .map(|node| {
                let len = match node {
                    Node::Decision { actions, .. } => N * actions.len(),
                    Node::Terminal { .. } => 0,
                };
                Mutex::new(NodeData {
                    regrets: vec![0.0; len],
                    strategy_sum: vec![0.0; len],
                })
            })
            .collect();
        Solver {
            tree,
            model,
            data,
            iteration: 0,
        }
    }

    pub fn iterations(&self) -> usize {
        self.iteration
    }

    pub fn run(&mut self, iterations: usize) {
        let players = self.tree.config.players;
        for _ in 0..iterations {
            self.iteration += 1;
            for p in 0..players {
                self.train(self.tree.root(), p, vec![prior(); players]);
            }
        }
    }

    /// 平均策略，布局与树的策略数组相同：每个决策节点 169 行、每行是各动作的概率。
    pub fn average_strategy(&self) -> Vec<f64> {
        let mut out = vec![0.0; self.tree.strategy_len];
        for (node, data) in self.tree.nodes.iter().zip(&self.data) {
            if let Node::Decision {
                actions, offset, ..
            } = node
            {
                let a = actions.len();
                let data = data.lock().unwrap();
                for h in 0..N {
                    let (i, j) = (offset + h * a, h * a);
                    regret_match(&data.strategy_sum[j..j + a], &mut out[i..i + a]);
                }
            }
        }
        out
    }

    fn train(&self, node: usize, p: usize, reach: Vec<Vec<f64>>) -> Vec<f64> {
        let tree = self.tree;
        match &tree.nodes[node] {
            Node::Terminal {
                contrib,
                alive,
                allin,
            } => terminal_values(tree, self.model, contrib, alive, *allin, p, &reach),
            Node::Decision {
                player,
                actions,
                children,
                ..
            } => {
                let a = actions.len();
                let mut sigma = vec![0.0; N * a];
                {
                    let data = self.data[node].lock().unwrap();
                    for h in 0..N {
                        let i = h * a;
                        regret_match(&data.regrets[i..i + a], &mut sigma[i..i + a]);
                    }
                }
                let values = branch(&reach, *player, children, &sigma, |child, reach| {
                    self.train(child, p, reach)
                });
                if *player != p {
                    return sum(values);
                }
                let weight = self.iteration as f64;
                let mut out = vec![0.0; N];
                let mut data = self.data[node].lock().unwrap();
                let NodeData {
                    regrets,
                    strategy_sum,
                } = &mut *data;
                for h in 0..N {
                    let i = h * a;
                    let s = &sigma[i..i + a];
                    let v: f64 = (0..a).map(|k| s[k] * values[k][h]).sum();
                    out[h] = v;
                    for k in 0..a {
                        regrets[i + k] = (regrets[i + k] + values[k][h] - v).max(0.0);
                        strategy_sum[i + k] += weight * reach[p][h] * s[k];
                    }
                }
                out
            }
        }
    }
}

/// 决策节点的每个动作分支：行动者的到达概率乘上该动作的概率，各分支并行求值。
fn branch(
    reach: &[Vec<f64>],
    player: usize,
    children: &[usize],
    sigma: &[f64],
    recurse: impl Fn(usize, Vec<Vec<f64>>) -> Vec<f64> + Sync,
) -> Vec<Vec<f64>> {
    let a = children.len();
    children
        .par_iter()
        .enumerate()
        .map(|(k, &child)| {
            let mut reach = reach.to_vec();
            for (h, r) in reach[player].iter_mut().enumerate() {
                *r *= sigma[h * a + k];
            }
            recurse(child, reach)
        })
        .collect()
}

fn sum(values: Vec<Vec<f64>>) -> Vec<f64> {
    values.into_iter().fold(vec![0.0; N], |mut acc, v| {
        for (a, x) in acc.iter_mut().zip(v) {
            *a += x;
        }
        acc
    })
}

/// 终局节点上 `p` 每种起手牌的反事实收益（已乘上其他所有玩家的到达概率）。
fn terminal_values(
    tree: &Tree,
    model: &Model,
    contrib: &[f32],
    alive: &[usize],
    allin: bool,
    p: usize,
    reach: &[Vec<f64>],
) -> Vec<f64> {
    let players = tree.config.players;
    let mass: Vec<f64> = reach.iter().map(|r| r.iter().sum()).collect();
    let others: f64 = (0..players).filter(|&j| j != p).map(|j| mass[j]).product();
    let pot: f64 = contrib.iter().map(|&c| c as f64).sum();
    let cost = contrib[p] as f64;

    if alive.len() == 1 {
        let won = if alive[0] == p { pot } else { 0.0 };
        return vec![(won - cost) * others; N];
    }
    if !alive.contains(&p) {
        return vec![-cost * others; N];
    }
    let opponents: Vec<usize> = alive.iter().copied().filter(|&j| j != p).collect();
    if opponents.iter().any(|&j| mass[j] <= 0.0) {
        return vec![-cost * others; N];
    }
    // 不在底池里的玩家（已弃牌）只贡献到达概率。
    let folded: f64 = (0..players)
        .filter(|&j| j != p && !alive.contains(&j))
        .map(|j| mass[j])
        .product();
    let share = pot_share(tree, model, alive, allin, p, reach);
    share
        .iter()
        .map(|s| folded * pot * s - cost * others)
        .collect()
}

/// 两两份额矩阵 K_ij：i 拿 h_i、j 拿 h_j 时，只看这两人 i 能分到的比例，满足 K_ij + K_ji = 1。
fn pair_matrix<'m>(tree: &Tree, model: &'m Model, allin: bool, i: usize, j: usize) -> &'m [f64] {
    let config = &tree.config;
    if allin {
        &model.equity
    } else if config.postflop_order(i) > config.postflop_order(j) {
        &model.share_ip
    } else {
        &model.share_oop
    }
}

/// `p` 拿每种起手牌时在底池 `alive` 里的期望份额（比例），已乘上底池内其他玩家的到达概率。
///
/// 对每一组具体手牌，玩家 l 独赢的近似概率是 P_l = Π_j K_lj，
/// 份额定为 P_l + (1 - Σ P) / k：剩下的部分（主要是近似误差和平局）由 k 人平分。
/// 这样每组手牌的份额之和恰好是 1，而且对每个玩家的范围都是线性的，
/// 求解的仍然是一个标准博弈。两人时就退化为 K_po。
fn pot_share(
    tree: &Tree,
    model: &Model,
    alive: &[usize],
    allin: bool,
    p: usize,
    reach: &[Vec<f64>],
) -> Vec<f64> {
    let k = alive.len() as f64;
    let opponents: Vec<usize> = alive.iter().copied().filter(|&j| j != p).collect();
    let mut tmp = vec![0.0; N];

    // Σ 的部分：E[P_p | h]，以及底池内对手的总到达概率。
    let mut own = vec![1.0; N];
    let mut opp_mass = 1.0;
    for &j in &opponents {
        mat_vec(pair_matrix(tree, model, allin, p, j), &reach[j], &mut tmp);
        for (o, t) in own.iter_mut().zip(&tmp) {
            *o *= t;
        }
        opp_mass *= reach[j].iter().sum::<f64>();
    }

    // 对手 l 独赢的部分：Σ_{h_l} u_l(h_l) K_lp(h_l, h)，u_l = r_l · Π_{j≠l,p} (K_lj r_j)。
    // 用 K_lp[h_l][h] = 1 - K_pl[h][h_l] 转成 K_pl 的矩阵乘法。
    let mut others_win = vec![0.0; N];
    for &l in &opponents {
        let mut u = reach[l].clone();
        for &j in opponents.iter().filter(|&&j| j != l) {
            mat_vec(pair_matrix(tree, model, allin, l, j), &reach[j], &mut tmp);
            for (x, t) in u.iter_mut().zip(&tmp) {
                *x *= t;
            }
        }
        let total: f64 = u.iter().sum();
        mat_vec(pair_matrix(tree, model, allin, p, l), &u, &mut tmp);
        for (o, t) in others_win.iter_mut().zip(&tmp) {
            *o += total - t;
        }
    }

    own.iter()
        .zip(&others_win)
        .map(|(mine, theirs)| mine + (opp_mass - mine - theirs) / k)
        .collect()
}

fn regret_match(values: &[f64], out: &mut [f64]) {
    let total: f64 = values.iter().map(|v| v.max(0.0)).sum();
    if total > 0.0 {
        for (o, v) in out.iter_mut().zip(values) {
            *o = v.max(0.0) / total;
        }
    } else {
        out.fill(1.0 / values.len() as f64);
    }
}

/// 某个策略下每位玩家的期望收益，以及各自改用最佳应对后的收益，单位 bb。
pub struct Report {
    pub ev: Vec<f64>,
    pub best_response: Vec<f64>,
}

impl Report {
    /// 每位玩家改用最佳应对能多赢多少（bb/手）。
    pub fn gains(&self) -> Vec<f64> {
        self.best_response
            .iter()
            .zip(&self.ev)
            .map(|(b, e)| b - e)
            .collect()
    }

    /// 所有玩家里最大的可提升幅度，换算成 bb/100 手。
    pub fn max_gain_per_100(&self) -> f64 {
        self.gains().into_iter().fold(0.0, f64::max) * 100.0
    }
}

pub fn evaluate(tree: &Tree, model: &Model, strategy: &[f64]) -> Report {
    let players = tree.config.players;
    let prior = prior();
    let value = |p: usize, best: bool| {
        let reach = vec![prior.clone(); players];
        let cfv = eval_node(tree, model, strategy, tree.root(), p, best, reach, None);
        cfv.iter().zip(&prior).map(|(v, w)| v * w).sum()
    };
    Report {
        ev: (0..players).map(|p| value(p, false)).collect(),
        best_response: (0..players).map(|p| value(p, true)).collect(),
    }
}

/// 平均策略下，每个决策节点上行动者拿每类起手牌选每个动作的期望收益，单位 bb，
/// 按整手牌的净输赢计（已扣掉此前投入的筹码），布局与策略数组相同。
/// 两个动作的差就是选错动作的 EV 损失。到达概率为 0 的节点记为 0。
pub fn action_values(tree: &Tree, model: &Model, strategy: &[f64]) -> Vec<f64> {
    let players = tree.config.players;
    let out = Mutex::new(vec![0.0; tree.strategy_len]);
    for p in 0..players {
        let reach = vec![prior(); players];
        eval_node(
            tree,
            model,
            strategy,
            tree.root(),
            p,
            false,
            reach,
            Some(&out),
        );
    }
    out.into_inner().unwrap()
}

/// `record` 不为空时，把 `p` 在自己决策节点上各动作的条件期望收益写进去。
#[allow(clippy::too_many_arguments)]
fn eval_node(
    tree: &Tree,
    model: &Model,
    strategy: &[f64],
    node: usize,
    p: usize,
    best: bool,
    reach: Vec<Vec<f64>>,
    record: Option<&Mutex<Vec<f64>>>,
) -> Vec<f64> {
    match &tree.nodes[node] {
        Node::Terminal {
            contrib,
            alive,
            allin,
        } => terminal_values(tree, model, contrib, alive, *allin, p, &reach),
        Node::Decision {
            player,
            actions,
            children,
            offset,
        } => {
            let a = actions.len();
            let sigma = &strategy[*offset..offset + N * a];
            let values = branch(&reach, *player, children, sigma, |child, reach| {
                eval_node(tree, model, strategy, child, p, best, reach, record)
            });
            if *player != p {
                return sum(values);
            }
            if let Some(record) = record {
                // 反事实收益已乘上其他人的到达概率，除掉后就是到达这里时的条件期望。
                let others: f64 = (0..reach.len())
                    .filter(|&j| j != p)
                    .map(|j| reach[j].iter().sum::<f64>())
                    .product();
                if others > 0.0 {
                    let mut record = record.lock().unwrap();
                    for h in 0..N {
                        for k in 0..a {
                            record[offset + h * a + k] = values[k][h] / others;
                        }
                    }
                }
            }
            (0..N)
                .map(|h| {
                    let actions = 0..a;
                    if best {
                        actions
                            .map(|k| values[k][h])
                            .fold(f64::NEG_INFINITY, f64::max)
                    } else {
                        actions.map(|k| sigma[h * a + k] * values[k][h]).sum()
                    }
                })
                .collect()
        }
    }
}
