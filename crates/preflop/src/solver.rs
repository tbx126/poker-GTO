use crate::model::{mat_vec, Model};
use crate::tree::{Node, Tree};
use holdem::{HandClass, NUM_CLASSES, TOTAL_COMBOS};

const N: usize = NUM_CLASSES;

/// 每种起手牌出现的先验概率（组合数 / 1326）。
pub fn prior() -> Vec<f64> {
    HandClass::all()
        .map(|h| h.num_combos() as f64 / TOTAL_COMBOS as f64)
        .collect()
}

/// 翻前 CFR+ 的 CPU 参考实现：按起手牌向量化遍历公开下注树。
/// 它的作用是给 GPU 版本当对照，速度不是重点。
pub struct Solver<'a> {
    tree: &'a Tree,
    model: &'a Model,
    regrets: Vec<f64>,
    strategy_sum: Vec<f64>,
    iteration: usize,
}

impl<'a> Solver<'a> {
    pub fn new(tree: &'a Tree, model: &'a Model) -> Self {
        Solver {
            tree,
            model,
            regrets: vec![0.0; tree.strategy_len],
            strategy_sum: vec![0.0; tree.strategy_len],
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
                let mut reach = vec![prior(); players];
                self.train(self.tree.root(), p, &mut reach);
            }
        }
    }

    /// 平均策略，布局与树的策略数组相同：每个决策节点 169 行、每行是各动作的概率。
    pub fn average_strategy(&self) -> Vec<f64> {
        let mut out = vec![0.0; self.tree.strategy_len];
        for node in &self.tree.nodes {
            if let Node::Decision {
                actions, offset, ..
            } = node
            {
                let a = actions.len();
                for h in 0..N {
                    let i = offset + h * a;
                    regret_match(&self.strategy_sum[i..i + a], &mut out[i..i + a]);
                }
            }
        }
        out
    }

    fn train(&mut self, node: usize, p: usize, reach: &mut [Vec<f64>]) -> Vec<f64> {
        let tree = self.tree;
        match &tree.nodes[node] {
            Node::Terminal {
                contrib,
                alive,
                allin,
            } => terminal_values(tree, self.model, contrib, alive, *allin, p, reach),
            Node::Decision {
                player,
                actions,
                children,
                offset,
            } => {
                let a = actions.len();
                let mut sigma = vec![0.0; N * a];
                for h in 0..N {
                    let i = offset + h * a;
                    regret_match(&self.regrets[i..i + a], &mut sigma[h * a..(h + 1) * a]);
                }
                if *player != p {
                    return opponent_node(reach, *player, children, &sigma, |child, reach| {
                        self.train(child, p, reach)
                    });
                }
                let values = own_node(reach, p, children, &sigma, |child, reach| {
                    self.train(child, p, reach)
                });
                let weight = self.iteration as f64;
                let mut out = vec![0.0; N];
                for h in 0..N {
                    let s = &sigma[h * a..(h + 1) * a];
                    let v: f64 = (0..a).map(|k| s[k] * values[k][h]).sum();
                    out[h] = v;
                    let i = offset + h * a;
                    for k in 0..a {
                        self.regrets[i + k] = (self.regrets[i + k] + values[k][h] - v).max(0.0);
                        self.strategy_sum[i + k] += weight * reach[p][h] * s[k];
                    }
                }
                out
            }
        }
    }
}

/// 对手节点：对手按各自策略分流到每个动作，`p` 的反事实收益是各分支之和。
fn opponent_node(
    reach: &mut [Vec<f64>],
    player: usize,
    children: &[usize],
    sigma: &[f64],
    mut recurse: impl FnMut(usize, &mut [Vec<f64>]) -> Vec<f64>,
) -> Vec<f64> {
    let a = children.len();
    let saved = reach[player].clone();
    let mut out = vec![0.0; N];
    for (k, &child) in children.iter().enumerate() {
        for h in 0..N {
            reach[player][h] = saved[h] * sigma[h * a + k];
        }
        for (o, v) in out.iter_mut().zip(recurse(child, reach)) {
            *o += v;
        }
    }
    reach[player] = saved;
    out
}

/// `p` 自己的节点：分别求每个动作的反事实收益。
/// 反事实收益本身不含 `p` 自己的到达概率，但多人底池的份额归一化要用到 `p` 的实际范围，
/// 所以往下传的 `reach[p]` 仍按 `p` 的策略分流。
fn own_node(
    reach: &mut [Vec<f64>],
    player: usize,
    children: &[usize],
    sigma: &[f64],
    mut recurse: impl FnMut(usize, &mut [Vec<f64>]) -> Vec<f64>,
) -> Vec<Vec<f64>> {
    let a = children.len();
    let saved = reach[player].clone();
    let values = children
        .iter()
        .enumerate()
        .map(|(k, &child)| {
            for h in 0..N {
                reach[player][h] = saved[h] * sigma[h * a + k];
            }
            recurse(child, reach)
        })
        .collect();
    reach[player] = saved;
    values
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
        let mut reach = vec![prior.clone(); players];
        let cfv = eval_node(tree, model, strategy, tree.root(), p, best, &mut reach);
        cfv.iter().zip(&prior).map(|(v, w)| v * w).sum()
    };
    Report {
        ev: (0..players).map(|p| value(p, false)).collect(),
        best_response: (0..players).map(|p| value(p, true)).collect(),
    }
}

fn eval_node(
    tree: &Tree,
    model: &Model,
    strategy: &[f64],
    node: usize,
    p: usize,
    best: bool,
    reach: &mut [Vec<f64>],
) -> Vec<f64> {
    match &tree.nodes[node] {
        Node::Terminal {
            contrib,
            alive,
            allin,
        } => terminal_values(tree, model, contrib, alive, *allin, p, reach),
        Node::Decision {
            player,
            actions,
            children,
            offset,
        } => {
            let a = actions.len();
            let sigma = &strategy[*offset..offset + N * a];
            if *player != p {
                return opponent_node(reach, *player, children, sigma, |child, reach| {
                    eval_node(tree, model, strategy, child, p, best, reach)
                });
            }
            // 最佳应对模式下 p 的范围仍按 `strategy` 计算，只在多人底池的归一化里用到。
            let values = own_node(reach, p, children, sigma, |child, reach| {
                eval_node(tree, model, strategy, child, p, best, reach)
            });
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
