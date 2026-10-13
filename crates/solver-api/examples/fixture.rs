//! 生成前端测试用的对照表：在求解树里随机走几条线，记下每个决策节点上求解器给出的动作。
//! 前端用自己的规则引擎重放同样的动作，检查合法动作和这里一致。
//! `cargo run --release -p solver-api --example fixture -- app/tests/fixtures/postflop-moves.json`

use holdem::Rng;
use postflop::{forbid_lead, tree_config, Sizes};
use postflop_solver::{Action as TreeAction, ActionTree, BoardState};
use preflop::{Config, Node, Tree};
use serde::Serialize;
use solver_api::line::{heads_up_seats, preflop_actions};
use solver_api::{MoveKind, PostflopMove};

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct Spot {
    players: usize,
    preflop: Vec<String>,
    board: Vec<String>,
    postflop: Vec<PostflopMove>,
    /// 当前行动的座位。
    seat: usize,
    /// 求解器在这个节点上的全部动作。
    actions: Vec<Expected>,
}

#[derive(Serialize, Clone)]
struct Expected {
    kind: MoveKind,
    to: f32,
}

const BOARD: [&str; 5] = ["Td", "9d", "6h", "2c", "5s"];

fn main() {
    let out = std::env::args()
        .nth(1)
        .unwrap_or("app/tests/fixtures/postflop-moves.json".into());
    let lines: Vec<(usize, Vec<&str>)> = vec![
        (2, vec!["SB 加注到 2.5", "BB 跟注"]),
        (2, vec!["SB 加注到 2.5", "BB 加注到 10", "SB 跟注"]),
        (
            2,
            vec!["SB 加注到 2.5", "BB 加注到 10", "SB 加注到 22.5", "BB 跟注"],
        ),
        (
            6,
            vec![
                "UTG 弃牌",
                "HJ 弃牌",
                "CO 弃牌",
                "BTN 加注到 2.5",
                "SB 弃牌",
                "BB 跟注",
            ],
        ),
        (
            6,
            vec![
                "UTG 弃牌",
                "HJ 弃牌",
                "CO 弃牌",
                "BTN 加注到 2.5",
                "SB 弃牌",
                "BB 加注到 10",
                "BTN 跟注",
            ],
        ),
        (
            6,
            vec![
                "UTG 加注到 2.5",
                "HJ 弃牌",
                "CO 弃牌",
                "BTN 弃牌",
                "SB 加注到 10",
                "BB 弃牌",
                "UTG 跟注",
            ],
        ),
    ];
    let mut rng = Rng::new(7);
    let mut spots = Vec::new();
    let mut seen = std::collections::HashSet::new();
    for (players, labels) in &lines {
        let labels: Vec<String> = labels.iter().map(|s| s.to_string()).collect();
        let tree = Tree::build(Config::new(*players));
        let path = preflop_actions(&tree, &labels).expect("翻前线不在树里");
        let seats = heads_up_seats(&tree, &path).expect("不是两人底池");
        let Node::Terminal { contrib, .. } = &tree.nodes[tree.follow(&path).unwrap()] else {
            panic!("翻前没有结束");
        };
        let pot0: f32 = contrib.iter().sum();
        let stack0 = tree.config.stack - contrib[seats[0]];
        for _ in 0..40 {
            walk(
                &mut rng, *players, &labels, seats, pot0, stack0, &mut spots, &mut seen,
            );
        }
    }
    std::fs::create_dir_all(std::path::Path::new(&out).parent().unwrap()).unwrap();
    std::fs::write(&out, serde_json::to_string_pretty(&spots).unwrap()).unwrap();
    println!("写入 {out}，{} 个局面", spots.len());
}

/// 从翻牌开始随机走一条线，每条街按引擎的做法用当街的尺寸重新建树。
#[allow(clippy::too_many_arguments)]
fn walk(
    rng: &mut Rng,
    players: usize,
    preflop: &[String],
    seats: [usize; 2],
    mut pot: f32,
    mut stack: f32,
    spots: &mut Vec<Spot>,
    seen: &mut std::collections::HashSet<String>,
) {
    let mut moves: Vec<PostflopMove> = Vec::new();
    for street in 1..=3 {
        let board_len = street + 2;
        let state = [BoardState::Flop, BoardState::Turn, BoardState::River][street - 1];
        let config = tree_config(pot, stack, &Sizes::precise(board_len), state).unwrap();
        let mut tree = ActionTree::new(config).unwrap();
        // 上一条街最后的进攻者是 IP 时，OOP 不能领先下注。
        let previous_aggressor = moves
            .iter()
            .rev()
            .find(|m| {
                m.street + 1 == street
                    && matches!(m.kind, MoveKind::Bet | MoveKind::Raise | MoveKind::Allin)
            })
            .map(|m| m.seat);
        if street > 1 && previous_aggressor == Some(seats[1]) {
            forbid_lead(&mut tree).unwrap();
        }
        loop {
            let bets = tree.total_bet_amount();
            let player = tree_player(&tree);
            let actions: Vec<Expected> = tree
                .available_actions()
                .iter()
                .map(|&a| to_move(a, bets, player))
                .collect();
            let board: Vec<String> = BOARD[..board_len].iter().map(|s| s.to_string()).collect();
            let key = format!("{players}{preflop:?}{board:?}{:?}", moves_key(&moves));
            if seen.insert(key) {
                spots.push(Spot {
                    players,
                    preflop: preflop.to_vec(),
                    board,
                    postflop: moves.clone(),
                    seat: seats[player],
                    actions: actions.clone(),
                });
            }
            let k = rng.below(actions.len());
            let action = tree.available_actions()[k];
            moves.push(PostflopMove {
                street,
                seat: seats[player],
                kind: actions[k].kind,
                to: actions[k].to,
            });
            tree.play(action).unwrap();
            if tree.is_terminal_node() {
                return;
            }
            if tree.is_chance_node() {
                let bets = tree.total_bet_amount();
                pot += 2.0 * postflop::to_bb(bets[0] as f32);
                stack -= postflop::to_bb(bets[0] as f32);
                break;
            }
        }
    }
}

/// 当前行动者：0 是 OOP，1 是 IP。每条街 OOP 先行动，之后轮流。
fn tree_player(tree: &ActionTree) -> usize {
    tree.history()
        .iter()
        .filter(|a| !matches!(a, TreeAction::Chance(_)))
        .count()
        % 2
}

fn to_move(a: TreeAction, bets: [i32; 2], player: usize) -> Expected {
    let (kind, chips) = match a {
        TreeAction::Fold => (MoveKind::Fold, bets[player]),
        TreeAction::Check => (MoveKind::Check, bets[player]),
        TreeAction::Call => (MoveKind::Call, bets[player ^ 1]),
        TreeAction::Bet(x) => (MoveKind::Bet, x),
        TreeAction::Raise(x) => (MoveKind::Raise, x),
        TreeAction::AllIn(x) => (MoveKind::Allin, x),
        _ => unreachable!(),
    };
    Expected {
        kind,
        to: postflop::to_bb(chips as f32),
    }
}

fn moves_key(moves: &[PostflopMove]) -> Vec<(usize, usize, MoveKind, i32)> {
    moves
        .iter()
        .map(|m| (m.street, m.seat, m.kind, (m.to * 100.0).round() as i32))
        .collect()
}
