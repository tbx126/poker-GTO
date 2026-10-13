//! 翻后求解的验收：两人底池在精确模式尺寸下，可剥削度降到底池的 0.3% 以下。

use holdem::parse_card;
use postflop::{
    build_game, next_street_spot, range_from_classes, solve, Outcome, Sizes, SolveOptions, Spot,
};
use postflop_solver::{Action as TreeAction, PostFlopGame};
use preflop::{follow_line, Action, Config, Model, Solver, Tree};
use std::sync::atomic::AtomicBool;

fn board(s: &str) -> Vec<u8> {
    (0..s.len() / 2)
        .map(|i| parse_card(&s[2 * i..2 * i + 2]).unwrap())
        .collect()
}

/// 两人桌小盲开池、大盲跟注后的局面，范围取自翻前求解。
fn hu_srp(cards: &str) -> Spot {
    let tree = Tree::build(Config::new(2));
    let model = Model::load_default().expect("缺少胜率表");
    let mut solver = Solver::new(&tree, &model);
    solver.run(300);
    let strategy = solver.average_strategy();
    let line = [Action::Raise(tree.config.open), Action::Call];
    let result = follow_line(&tree, &strategy, &line).unwrap();
    Spot {
        board: board(cards),
        // 两人桌翻后大盲（座位 1）没位置
        ranges: [
            range_from_classes(&result.ranges[1]),
            range_from_classes(&result.ranges[0]),
        ],
        pot: result.contrib.iter().sum(),
        stack: tree.config.stack - result.contrib[1],
        oop_can_lead: true,
    }
}

fn solve_to_target(game: &mut PostFlopGame) -> f32 {
    let options = SolveOptions::default();
    let (outcome, last) = solve(game, &options, &AtomicBool::new(false), |_| {});
    assert_eq!(
        outcome,
        Outcome::Converged,
        "可剥削度 {}",
        last.exploitability
    );
    assert!(last.exploitability < 0.003);
    last.exploitability
}

#[test]
fn srp_pot_and_stack() {
    let spot = hu_srp("Ks7h2d");
    assert_eq!(spot.pot, 5.0);
    assert_eq!(spot.stack, 97.5);
}

#[test]
fn river_converges() {
    let spot = hu_srp("Ks7h2dTc4s");
    let mut game = build_game(&spot, &Sizes::precise(5), false).unwrap();
    solve_to_target(&mut game);
}

#[test]
fn turn_converges_and_river_resolves() {
    let spot = hu_srp("Qh8c3dJs");
    let mut game = build_game(&spot, &Sizes::precise(4), false).unwrap();
    solve_to_target(&mut game);

    // 转牌双方过牌，河牌发 2c，用走到这里的范围重新求解河牌。
    for _ in 0..2 {
        let check = game
            .available_actions()
            .iter()
            .position(|&a| a == TreeAction::Check)
            .unwrap();
        game.play(check);
    }
    assert!(game.is_chance_node());
    game.play(parse_card("2c").unwrap() as usize);
    let river = next_street_spot(&mut game).unwrap();
    assert!(river.oop_can_lead);
    assert_eq!(river.board, board("Qh8c3dJs2c"));
    assert_eq!(river.pot, spot.pot);
    assert_eq!(river.stack, spot.stack);
    // 过牌线上的范围比原来窄，但不会是空的。
    for player in 0..2 {
        let before: f32 = spot.ranges[player].raw_data().iter().sum();
        let after: f32 = river.ranges[player].raw_data().iter().sum();
        assert!(after > 0.0 && after < before);
    }
    let mut river_game = build_game(&river, &Sizes::precise(5), false).unwrap();
    solve_to_target(&mut river_game);
}
