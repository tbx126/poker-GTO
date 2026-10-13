//! 打印 2 到 6 人下注树的规模：`cargo run --release --example size`
use preflop::{Config, Node, Tree};

fn main() {
    for players in 2..=6 {
        let tree = Tree::build(Config::new(players));
        let terminals = tree.nodes.len() - tree.num_decisions();
        let showdowns = tree
            .nodes
            .iter()
            .filter(|n| matches!(n, Node::Terminal { alive, .. } if alive.len() > 1))
            .count();
        println!(
            "{players} 人：{} 个决策节点，{terminals} 个终局（其中摊牌 {showdowns} 个），策略数组 {} 格",
            tree.num_decisions(),
            tree.strategy_len
        );
    }
}
