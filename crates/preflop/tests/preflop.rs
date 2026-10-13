use holdem::HandClass;
use preflop::{evaluate, Action, Config, Model, Node, Solver, Tree};

fn actions_at(tree: &Tree, path: &[Action]) -> (usize, Vec<Action>) {
    match &tree.nodes[tree.follow(path).expect("路径存在")] {
        Node::Decision {
            player, actions, ..
        } => (*player, actions.clone()),
        Node::Terminal { .. } => panic!("{path:?} 是终局"),
    }
}

#[test]
fn heads_up_tree_has_expected_sizes() {
    use Action::*;
    let tree = Tree::build(Config::new(2));
    // 小盲先行动：弃牌或开池到 2.5bb，不允许溜进。
    assert_eq!(actions_at(&tree, &[]), (0, vec![Fold, Raise(2.5)]));
    // 大盲翻后没位置，3bet 到 4 倍。
    assert_eq!(
        actions_at(&tree, &[Raise(2.5)]),
        (1, vec![Fold, Call, Raise(10.0)])
    );
    // 小盲有位置，4bet 到 2.25 倍，另外可以全下。
    assert_eq!(
        actions_at(&tree, &[Raise(2.5), Raise(10.0)]),
        (0, vec![Fold, Call, Raise(22.5), AllIn])
    );
    assert_eq!(
        actions_at(&tree, &[Raise(2.5), Raise(10.0), Raise(22.5)]),
        (1, vec![Fold, Call, AllIn])
    );

    let Node::Terminal {
        contrib,
        alive,
        allin,
    } = &tree.nodes[tree.follow(&[Fold]).unwrap()]
    else {
        panic!()
    };
    assert_eq!(
        (contrib.as_slice(), alive.as_slice(), *allin),
        (&[0.5, 1.0][..], &[1][..], false)
    );

    let Node::Terminal { contrib, allin, .. } = &tree.nodes[tree
        .follow(&[Raise(2.5), Raise(10.0), AllIn, Call])
        .unwrap()]
    else {
        panic!()
    };
    assert_eq!((contrib.as_slice(), *allin), (&[100.0, 100.0][..], true));
}

#[test]
fn six_max_order_and_squeeze_sizing() {
    use Action::*;
    let config = Config::new(6);
    assert_eq!(
        (0..6).map(|s| config.position_name(s)).collect::<Vec<_>>(),
        ["UTG", "HJ", "CO", "BTN", "SB", "BB"]
    );
    let tree = Tree::build(config);
    // UTG 开池，HJ 跟注，CO 有位置 3bet：3 × 2.5 + 1 个跟注者 × 2.5 = 10。
    assert_eq!(
        actions_at(&tree, &[Raise(2.5), Call]),
        (2, vec![Fold, Call, Raise(10.0)])
    );
    // 一路弃牌到大盲：大盲直接赢下盲注，不再行动。
    let all_fold = [Fold, Fold, Fold, Fold, Fold];
    assert!(matches!(
        &tree.nodes[tree.follow(&all_fold).unwrap()],
        Node::Terminal { alive, .. } if alive == &[5]
    ));
    // 开池后其他人都弃牌，开池者还要等大盲行动，大盲弃牌后底池结束。
    let path = [Raise(2.5), Fold, Fold, Fold, Fold];
    assert_eq!(actions_at(&tree, &path).0, 5);
}

fn solve(players: usize, iterations: usize) -> (Tree, Model, Vec<f64>) {
    let tree = Tree::build(Config::new(players));
    let model = Model::load_default().expect("缺少胜率表");
    let strategy = {
        let mut solver = Solver::new(&tree, &model);
        solver.run(iterations);
        solver.average_strategy()
    };
    (tree, model, strategy)
}

#[test]
fn payoffs_are_zero_sum() {
    for players in [2, 3] {
        let (tree, model, strategy) = solve(players, 20);
        let total: f64 = evaluate(&tree, &model, &strategy).ev.iter().sum();
        assert!(total.abs() < 1e-9, "{players} 人总收益 {total}");
    }
}

#[test]
fn heads_up_converges() {
    let (tree, model, early) = solve(2, 20);
    let early = evaluate(&tree, &model, &early).max_gain_per_100();
    let (tree, model, strategy) = solve(2, 1_000);
    let report = evaluate(&tree, &model, &strategy);
    let late = report.max_gain_per_100();
    assert!(late < early / 4.0, "20 轮 {early}，1000 轮 {late}");
    assert!(late < 1.0, "可剥削度 {late} bb/100");

    // AA 在小盲永远开池，72o 在小盲不会每次都开池。
    let Node::Decision { offset, .. } = &tree.nodes[tree.root()] else {
        panic!()
    };
    let raise_freq =
        |name: &str| strategy[offset + HandClass::from_name(name).unwrap().index() * 2 + 1];
    assert!(raise_freq("AA") > 0.99);
    assert!(raise_freq("72o") < raise_freq("AA"));
}

#[test]
fn three_handed_improves_with_iterations() {
    let (tree, model, early) = solve(3, 10);
    let early = evaluate(&tree, &model, &early).max_gain_per_100();
    let (tree, model, late) = solve(3, 200);
    let late = evaluate(&tree, &model, &late).max_gain_per_100();
    assert!(late < early / 2.0, "10 轮 {early}，200 轮 {late}");
}

#[test]
fn saved_strategy_round_trips() {
    use preflop::{load, save, Meta};
    let (tree, _, strategy) = solve(3, 30);
    let meta = Meta {
        iterations: 30,
        max_gain_per_100: 1.5,
    };
    let mut bytes = Vec::new();
    save(&mut bytes, &tree, &strategy, &meta).unwrap();
    let (config, loaded, meta) = load(bytes.as_slice()).unwrap();
    assert_eq!(config.players, 3);
    assert_eq!(config.open, 2.5);
    assert_eq!(meta.iterations, 30);
    assert_eq!(loaded.len(), strategy.len());
    // 量化误差小于一个刻度，每行概率之和仍为 1。
    for (a, b) in loaded.iter().zip(&strategy) {
        assert!((a - b).abs() < 1.0 / 255.0);
    }
    let Node::Decision {
        offset, actions, ..
    } = &tree.nodes[tree.root()]
    else {
        panic!()
    };
    let row: f64 = loaded[*offset..offset + actions.len()].iter().sum();
    assert!((row - 1.0).abs() < 1e-9);
}
