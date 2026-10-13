use cfr::games::{Kuhn, Leduc};
use cfr::{expected_value, exploitability, Solver, Strategy, Tree};

#[test]
fn kuhn_uniform_strategy_is_exploitable() {
    let tree = Tree::build(&Kuhn);
    assert_eq!(tree.infosets.len(), 12);
    let uniform = Strategy::uniform(&tree);
    // 均匀随机策略在库恩扑克里的可剥削度已知为 0.4583。
    assert!((exploitability(&tree, &uniform) - 0.458_333).abs() < 1e-3);
}

#[test]
fn kuhn_converges_to_known_value() {
    let tree = Tree::build(&Kuhn);
    let mut solver = Solver::new(&tree);
    solver.run(2_000);
    let strategy = solver.average_strategy();

    let exploit = exploitability(&tree, &strategy);
    assert!(exploit < 1e-3, "可剥削度 {exploit}");
    let value = expected_value(&tree, &strategy);
    assert!((value + 1.0 / 18.0).abs() < 2e-3, "先手收益 {value}");

    // 持 K 的后手面对下注必须跟注，持 J 的后手面对下注必须弃牌。
    let call_with_king = tree.infoset_id("1|2:[1]").unwrap();
    assert!(strategy.probs[call_with_king][1] > 0.99);
    let fold_with_jack = tree.infoset_id("1|0:[1]").unwrap();
    assert!(strategy.probs[fold_with_jack][0] > 0.99);
}

#[test]
fn leduc_converges_to_known_value() {
    let tree = Tree::build(&Leduc);
    // 花色不影响牌力，按点数合并后是 288 个信息集（区分花色时为 936 个）。
    assert_eq!(tree.infosets.len(), 288);
    let mut solver = Solver::new(&tree);
    solver.run(2_000);
    let strategy = solver.average_strategy();

    let exploit = exploitability(&tree, &strategy);
    assert!(exploit < 5e-3, "可剥削度 {exploit}");
    let value = expected_value(&tree, &strategy);
    assert!((value + 0.0856).abs() < 5e-3, "先手收益 {value}");
}

#[test]
fn exploitability_falls_as_iterations_grow() {
    let tree = Tree::build(&Leduc);
    let mut solver = Solver::new(&tree);
    solver.run(50);
    let early = exploitability(&tree, &solver.average_strategy());
    solver.run(450);
    let late = exploitability(&tree, &solver.average_strategy());
    assert!(late < early / 2.0, "50 轮 {early}，500 轮 {late}");
}
