//! 打印库恩扑克和 Leduc 的收敛过程：`cargo run --release --example convergence`
use cfr::games::{Kuhn, Leduc};
use cfr::{expected_value, exploitability, Game, Solver, Tree};

fn report<G: Game>(name: &str, game: &G) {
    let tree = Tree::build(game);
    let mut solver = Solver::new(&tree);
    println!(
        "{name}：{} 个节点，{} 个信息集",
        tree.nodes.len(),
        tree.infosets.len()
    );
    for target in [10, 100, 1_000, 10_000] {
        solver.run(target - solver.iterations());
        let s = solver.average_strategy();
        println!(
            "  {target:>6} 轮  可剥削度 {:.6}  先手收益 {:.5}",
            exploitability(&tree, &s),
            expected_value(&tree, &s)
        );
    }
}

fn main() {
    report("库恩扑克", &Kuhn);
    report("Leduc", &Leduc);
}
