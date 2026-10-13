//! 多人底池的规则近似：用仓库里的六人桌范围表，CO 开池、BTN 和 BB 跟注的三人底池。

use solver_api::{
    ApproxStrategy, Engine, EngineOptions, HandState, LegalMove, MoveKind, PostflopMove,
};
use std::path::Path;

const CO: usize = 2;
const BTN: usize = 3;
const BB: usize = 5;

fn engine() -> Engine {
    let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../data/preflop");
    Engine::new(&dir, EngineOptions::default())
}

fn mv(street: usize, seat: usize, kind: MoveKind, to: f32) -> PostflopMove {
    PostflopMove {
        street,
        seat,
        kind,
        to,
    }
}

fn legal(moves: &[(MoveKind, f32)]) -> Vec<LegalMove> {
    moves
        .iter()
        .map(|&(kind, to)| LegalMove { kind, to })
        .collect()
}

fn hand(board: &[&str], postflop: Vec<PostflopMove>, seat: usize, cards: [&str; 2]) -> HandState {
    let mut all = [
        ["2s", "3c"],
        ["4c", "5c"],
        ["Ac", "Kc"],
        ["Qs", "Qh"],
        ["7c", "8c"],
        ["6s", "6c"],
    ];
    all[seat] = cards;
    HandState {
        hand_id: "approx".into(),
        players: 6,
        preflop: [
            "UTG 弃牌",
            "HJ 弃牌",
            "CO 加注到 2.5",
            "BTN 跟注",
            "SB 弃牌",
            "BB 跟注",
        ]
        .map(String::from)
        .to_vec(),
        board: board.iter().map(|c| c.to_string()).collect(),
        postflop,
        cards: all.iter().map(|p| p.map(String::from)).collect(),
    }
}

fn freq(s: &ApproxStrategy, kinds: &[MoveKind]) -> f32 {
    s.actions
        .iter()
        .filter(|a| kinds.contains(&a.kind))
        .map(|a| a.freq)
        .sum()
}

const FLOP: [&str; 3] = ["Td", "9d", "6h"];
const RIVER: [&str; 5] = ["Td", "9d", "6h", "2c", "Ks"];

/// 河牌前的行动：翻牌 BB 过牌、CO 下注、两人跟注，转牌三人都过牌。
fn to_river() -> Vec<PostflopMove> {
    vec![
        mv(1, BB, MoveKind::Check, 0.0),
        mv(1, CO, MoveKind::Bet, 2.6),
        mv(1, BTN, MoveKind::Call, 2.6),
        mv(1, BB, MoveKind::Call, 2.6),
        mv(2, BB, MoveKind::Check, 0.0),
        mv(2, CO, MoveKind::Check, 0.0),
        mv(2, BTN, MoveKind::Check, 0.0),
    ]
}

#[test]
fn strong_hands_bet_and_weak_hands_check() {
    let engine = engine();
    let moves = legal(&[
        (MoveKind::Check, 0.0),
        (MoveKind::Bet, 2.64),
        (MoveKind::Bet, 6.0),
        (MoveKind::Allin, 97.5),
    ]);
    let set = engine
        .approx(&hand(&FLOP, vec![], BB, ["6s", "6c"]), BB, &moves)
        .unwrap();
    let air = engine
        .approx(&hand(&FLOP, vec![], BB, ["Ks", "3h"]), BB, &moves)
        .unwrap();
    for s in [&set, &air] {
        assert_eq!(s.actions.len(), moves.len());
        let total: f32 = s.actions.iter().map(|a| a.freq).sum();
        assert!((total - 1.0).abs() < 1e-4);
        for (a, m) in s.actions.iter().zip(&moves) {
            assert_eq!((a.kind, a.to), (m.kind, m.to));
        }
    }
    assert!(set.equity > 0.7, "{set:?}");
    assert!(air.equity < 0.2, "{air:?}");
    assert!(
        freq(&set, &[MoveKind::Bet, MoveKind::Allin]) > 0.9,
        "{set:?}"
    );
    assert!(freq(&air, &[MoveKind::Check]) > 0.5, "{air:?}");
    assert_eq!(freq(&air, &[MoveKind::Allin]), 0.0, "{air:?}");
}

#[test]
fn a_bet_narrows_the_bettor_range() {
    let engine = engine();
    let qq = ["Qs", "Qh"];
    let mut checked = to_river();
    checked.push(mv(3, BB, MoveKind::Check, 0.0));
    checked.push(mv(3, CO, MoveKind::Check, 0.0));
    let mut bet = to_river();
    bet.push(mv(3, BB, MoveKind::Bet, 12.0));
    bet.push(mv(3, CO, MoveKind::Fold, 0.0));

    let quiet = engine
        .approx(
            &hand(&RIVER, checked, BTN, qq),
            BTN,
            &legal(&[(MoveKind::Check, 0.0), (MoveKind::Bet, 5.2)]),
        )
        .unwrap();
    let facing = engine
        .approx(
            &hand(&RIVER, bet, BTN, qq),
            BTN,
            &legal(&[(MoveKind::Fold, 0.0), (MoveKind::Call, 12.0)]),
        )
        .unwrap();
    assert!(
        facing.equity + 0.15 < quiet.equity,
        "被下注后胜率应明显更低：{} vs {}",
        facing.equity,
        quiet.equity
    );
}

#[test]
fn air_folds_to_a_big_river_bet() {
    let engine = engine();
    let mut moves = to_river();
    moves.push(mv(3, BB, MoveKind::Bet, 12.0));
    moves.push(mv(3, CO, MoveKind::Fold, 0.0));
    let s = engine
        .approx(
            &hand(&RIVER, moves, BTN, ["Js", "8h"]),
            BTN,
            &legal(&[
                (MoveKind::Fold, 0.0),
                (MoveKind::Call, 12.0),
                (MoveKind::Raise, 36.0),
                (MoveKind::Allin, 94.9),
            ]),
        )
        .unwrap();
    assert!(freq(&s, &[MoveKind::Fold]) > 0.9, "{s:?}");
}

#[test]
fn rejects_a_seat_that_folded_preflop() {
    let state = hand(&FLOP, vec![], BB, ["6s", "6c"]);
    let moves = legal(&[(MoveKind::Check, 0.0)]);
    assert!(engine().approx(&state, 0, &moves).is_err());
}
