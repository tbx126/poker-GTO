//! 用两人桌范围表走一手 4bet 底池：翻牌后台求解、取策略、按策略行动，再到转牌重新求解。

use preflop::{save, Config, Meta, Model, Solver, Tree};
use solver_api::{Engine, EngineOptions, HandState, MoveKind, PostflopMove, Progress};
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::Duration;

fn tables_dir() -> PathBuf {
    let dir = std::env::temp_dir().join(format!("solver-api-test-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let tree = Tree::build(Config::new(2));
    let model = Model::load_default().expect("缺少胜率表");
    let mut solver = Solver::new(&tree, &model);
    solver.run(300);
    let meta = Meta {
        iterations: 300,
        max_gain_per_100: 0.0,
    };
    let file = std::fs::File::create(dir.join("2max.bin")).unwrap();
    save(file, &tree, &solver.average_strategy(), &meta).unwrap();
    dir
}

fn engine() -> Engine {
    let options = EngineOptions {
        target: 0.01,
        time_limit: Duration::from_secs(120),
        max_iterations: 300,
    };
    Engine::new(&tables_dir(), options)
}

fn hand(board: &[&str], postflop: Vec<PostflopMove>) -> HandState {
    HandState {
        hand_id: "test-1".into(),
        players: 2,
        // 两人桌：座位 0 是小盲（翻后有位置），座位 1 是大盲。
        // 4bet 底池筹码底池比低，求解树小，测试跑得快。
        preflop: vec![
            "SB 加注到 2.5".into(),
            "BB 加注到 10".into(),
            "SB 加注到 22.5".into(),
            "BB 跟注".into(),
        ],
        board: board.iter().map(|s| s.to_string()).collect(),
        postflop,
        cards: vec![["Ah".into(), "Kh".into()], ["Qs".into(), "Qc".into()]],
    }
}

fn mv(street: usize, seat: usize, kind: MoveKind, to: f32) -> PostflopMove {
    PostflopMove {
        street,
        seat,
        kind,
        to,
    }
}

#[test]
fn heads_up_four_bet_pot_across_streets() {
    let engine = engine();
    let flop = hand(&["Kd", "8c", "3s"], vec![]);
    assert!(engine.supports(&flop));

    let seen: Arc<Mutex<Vec<Progress>>> = Arc::default();
    let sink = seen.clone();
    engine
        .prepare(&flop, move |p| sink.lock().unwrap().push(p))
        .unwrap();

    // 大盲先行动。小盲现在不能行动。
    assert!(engine.strategy(&flop, 0).is_err());
    let bb = engine.strategy(&flop, 1).unwrap();
    let progress = seen.lock().unwrap().clone();
    assert!(progress.last().unwrap().done);
    assert!(progress
        .windows(2)
        .all(|w| w[0].fraction <= w[1].fraction + 1e-6));
    assert!(bb.exploitability < 0.01);
    check_strategy(&bb.actions);
    assert_eq!(bb.actions[0].kind, MoveKind::Check);

    // 大盲过牌，小盲 AK 在 K 高牌面上拿着顶对，下注的频率应该不低。
    let after_check = hand(&["Kd", "8c", "3s"], vec![mv(1, 1, MoveKind::Check, 0.0)]);
    let sb = engine.strategy(&after_check, 0).unwrap();
    check_strategy(&sb.actions);
    let bet = sb
        .actions
        .iter()
        .find(|a| a.kind == MoveKind::Bet)
        .unwrap()
        .clone();

    // 小盲下注、大盲跟注，发转牌 2h，转牌重新求解，大盲先行动。
    let turn = hand(
        &["Kd", "8c", "3s", "2h"],
        vec![
            mv(1, 1, MoveKind::Check, 0.0),
            mv(1, 0, MoveKind::Bet, bet.to),
            mv(1, 1, MoveKind::Call, bet.to),
        ],
    );
    let bb_turn = engine.strategy(&turn, 1).unwrap();
    check_strategy(&bb_turn.actions);
    assert!(bb_turn.exploitability < 0.01);

    engine.cancel("test-1");
}

#[test]
fn multiway_and_unknown_lines_are_not_supported() {
    let engine = engine();
    let mut state = hand(&["Kd", "8c", "3s"], vec![]);
    state.preflop = vec!["SB 加注到 2.5".into(), "BB 弃牌".into()];
    assert!(!engine.supports(&state));
    state.preflop = vec!["SB 加注到 3".into()];
    assert!(!engine.supports(&state));
}

/// 频率加起来是 1；均衡里常用的动作 EV 都接近这手牌最好的动作。
fn check_strategy(actions: &[solver_api::ActionAdvice]) {
    let total: f32 = actions.iter().map(|a| a.freq).sum();
    assert!((total - 1.0).abs() < 1e-3, "频率之和 {total}");
    let best = actions.iter().map(|a| a.ev).fold(f32::MIN, f32::max);
    for a in actions {
        if a.freq > 0.2 {
            assert!(best - a.ev < 1.0, "{actions:?}");
        }
    }
}
