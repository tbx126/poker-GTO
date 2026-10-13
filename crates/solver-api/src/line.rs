//! 把前端的手牌状态翻译成求解器认识的东西：翻前行动线、座位角色、翻后动作。

use crate::types::{HandState, MoveKind, PostflopMove};
use holdem::{parse_card, Card};
use postflop_solver::Action as TreeAction;
use preflop::{action_label, Action, Node, Tree};

/// 按“位置 动作”标签沿翻前树走，得到动作序列。
pub fn preflop_actions(tree: &Tree, labels: &[String]) -> Result<Vec<Action>, String> {
    let mut node = tree.root();
    let mut path = Vec::new();
    for label in labels {
        let Node::Decision {
            player,
            actions,
            children,
            ..
        } = &tree.nodes[node]
        else {
            return Err(format!("翻前已经结束，多出动作：{label}"));
        };
        let position = tree.config.position_name(*player);
        let k = actions
            .iter()
            .position(|&a| format!("{position} {}", action_label(a)) == *label)
            .ok_or_else(|| format!("翻前树里没有这个动作：{label}"))?;
        path.push(actions[k]);
        node = children[k];
    }
    Ok(path)
}

/// 翻前结束时还在的两个座位，按翻后行动顺序排成 [OOP, IP]。不是两人底池时返回 None。
pub fn heads_up_seats(tree: &Tree, path: &[Action]) -> Option<[usize; 2]> {
    let node = tree.follow(path)?;
    let Node::Terminal { alive, allin, .. } = &tree.nodes[node] else {
        return None;
    };
    if alive.len() != 2 || *allin {
        return None;
    }
    let (a, b) = (alive[0], alive[1]);
    let config = &tree.config;
    Some(if config.postflop_order(a) < config.postflop_order(b) {
        [a, b]
    } else {
        [b, a]
    })
}

pub fn parse_cards(names: &[String]) -> Result<Vec<Card>, String> {
    names
        .iter()
        .map(|c| parse_card(c).ok_or_else(|| format!("看不懂的牌：{c}")))
        .collect()
}

pub fn hole_cards(state: &HandState, seat: usize) -> Result<(Card, Card), String> {
    let pair = state
        .cards
        .get(seat)
        .ok_or_else(|| format!("没有座位 {seat} 的底牌"))?;
    let cards = parse_cards(pair)?;
    Ok((cards[0].min(cards[1]), cards[0].max(cards[1])))
}

/// 这条街上已经发生的动作。
pub fn street_moves(state: &HandState, street: usize) -> Vec<&PostflopMove> {
    state
        .postflop
        .iter()
        .filter(|m| m.street == street)
        .collect()
}

/// 在求解树的可选动作里找出和前端动作对应的那个。
/// 弃牌、过牌、跟注要求种类相同；下注、加注、全下都算主动投注，取金额最接近的，
/// 这样前后端尺寸的取整差异不会让对应失败。
pub fn match_action(actions: &[TreeAction], kind: MoveKind, to_chips: i32) -> Option<usize> {
    let exact = |a: &TreeAction| {
        matches!(
            (kind, a),
            (MoveKind::Fold, TreeAction::Fold)
                | (MoveKind::Check, TreeAction::Check)
                | (MoveKind::Call, TreeAction::Call)
        )
    };
    if let Some(i) = actions.iter().position(exact) {
        return Some(i);
    }
    if !matches!(kind, MoveKind::Bet | MoveKind::Raise | MoveKind::Allin) {
        return None;
    }
    actions
        .iter()
        .enumerate()
        .filter_map(|(i, a)| match *a {
            TreeAction::Bet(x) | TreeAction::Raise(x) | TreeAction::AllIn(x) => {
                // 前端说全下时，只接受求解器的全下或同等金额。
                let penalty = if kind == MoveKind::Allin && !matches!(a, TreeAction::AllIn(_)) {
                    1
                } else {
                    0
                };
                Some((i, (penalty, (x - to_chips).abs())))
            }
            _ => None,
        })
        .min_by_key(|&(_, key)| key)
        .map(|(i, _)| i)
}
