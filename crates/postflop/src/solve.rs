use crate::{to_chips, Sizes};
use holdem::Card;
use postflop_solver::{
    compute_exploitability, finalize, solve_step, Action as TreeAction, ActionTree, BoardState,
    CardConfig, PostFlopGame, Range, TreeConfig, NOT_DEALT,
};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

/// 一个两人翻后局面。座位 0 是没位置的一方（OOP），座位 1 有位置（IP）。
pub struct Spot {
    /// 3 到 5 张公共牌。
    pub board: Vec<Card>,
    /// [OOP, IP] 的范围。
    pub ranges: [Range; 2],
    /// 当前底池，单位 bb。
    pub pot: f32,
    /// 双方剩余的有效筹码，单位 bb。
    pub stack: f32,
    /// OOP 能否在这条街领先下注。上一条街最后的进攻者是 IP 时不能（不设领先下注）。
    pub oop_can_lead: bool,
}

/// 按局面和下注尺寸建好博弈树并分配内存。
/// `compress` 为真时策略用 16 位整数存，内存约减半，速度略慢。
pub fn build_game(spot: &Spot, sizes: &Sizes, compress: bool) -> Result<PostFlopGame, String> {
    let mut game = build_game_unallocated(spot, sizes)?;
    game.allocate_memory(compress);
    Ok(game)
}

/// 只建树、不分配求解内存，可以先用 `memory_usage` 估算内存。
pub fn build_game_unallocated(spot: &Spot, sizes: &Sizes) -> Result<PostFlopGame, String> {
    let (initial_state, turn, river) = match spot.board.len() {
        3 => (BoardState::Flop, NOT_DEALT, NOT_DEALT),
        4 => (BoardState::Turn, spot.board[3], NOT_DEALT),
        5 => (BoardState::River, spot.board[3], spot.board[4]),
        n => return Err(format!("公共牌应为 3 到 5 张，实际 {n} 张")),
    };
    let card_config = CardConfig {
        range: spot.ranges,
        flop: [spot.board[0], spot.board[1], spot.board[2]],
        turn,
        river,
    };
    let tree_config = tree_config(spot.pot, spot.stack, sizes, initial_state)?;
    let mut tree = ActionTree::new(tree_config)?;
    if !spot.oop_can_lead {
        forbid_lead(&mut tree)?;
    }
    PostFlopGame::with_config(card_config, tree)
}

/// 博弈树的配置：底池和有效筹码（bb）、从哪条街开始、各街下注尺寸。
pub fn tree_config(
    pot: f32,
    stack: f32,
    sizes: &Sizes,
    initial_state: BoardState,
) -> Result<TreeConfig, String> {
    let flop = sizes.flop.options()?;
    let turn = sizes.turn.options()?;
    let river = sizes.river.options()?;
    let donk = sizes.donk_options()?;
    Ok(TreeConfig {
        initial_state,
        starting_pot: to_chips(pot),
        effective_stack: to_chips(stack),
        rake_rate: 0.0,
        rake_cap: 0.0,
        flop_bet_sizes: [flop.clone(), flop],
        turn_bet_sizes: [turn.clone(), turn],
        river_bet_sizes: [river.clone(), river],
        turn_donk_sizes: donk.clone(),
        river_donk_sizes: donk,
        add_allin_threshold: sizes.add_allin_threshold,
        force_allin_threshold: sizes.force_allin_threshold,
        merging_threshold: sizes.merging_threshold,
    })
}

/// 去掉根节点上 OOP 的下注和全下，只留过牌。
pub fn forbid_lead(tree: &mut ActionTree) -> Result<(), String> {
    let leads: Vec<TreeAction> = tree
        .available_actions()
        .iter()
        .copied()
        .filter(|a| matches!(a, TreeAction::Bet(_) | TreeAction::AllIn(_)))
        .collect();
    for a in leads {
        tree.remove_line(&[a])?;
    }
    Ok(())
}

pub struct SolveOptions {
    /// 可剥削度降到底池的这个比例以下就停，0.003 即 0.3%。
    pub target: f32,
    pub max_iterations: u32,
    /// 每隔多少轮算一次可剥削度并回报进度。
    pub check_every: u32,
    /// 超过这个时间就停下，用当时的策略。
    pub time_limit: Option<Duration>,
}

impl Default for SolveOptions {
    fn default() -> SolveOptions {
        SolveOptions {
            target: 0.003,
            max_iterations: 2000,
            check_every: 10,
            time_limit: None,
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Progress {
    pub iteration: u32,
    /// 可剥削度占起始底池的比例。
    pub exploitability: f32,
    pub elapsed: Duration,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Outcome {
    /// 达到目标精度。
    Converged,
    /// 用完了迭代次数或时间。
    Exhausted,
    /// 被外部取消（比如玩家已经行动）。
    Cancelled,
}

/// 求解到目标精度、用完预算或被取消为止，最后把平均策略定下来。
/// 每次检查可剥削度时调用一次 `on_progress`。
pub fn solve(
    game: &mut PostFlopGame,
    options: &SolveOptions,
    cancel: &AtomicBool,
    mut on_progress: impl FnMut(Progress),
) -> (Outcome, Progress) {
    let start = Instant::now();
    let pot = game.tree_config().starting_pot as f32;
    let mut progress = Progress {
        iteration: 0,
        exploitability: compute_exploitability(game) / pot,
        elapsed: start.elapsed(),
    };
    on_progress(progress);
    let mut outcome = Outcome::Exhausted;
    let mut t = 0;
    while t < options.max_iterations {
        if progress.exploitability <= options.target {
            outcome = Outcome::Converged;
            break;
        }
        if cancel.load(Ordering::Relaxed) {
            outcome = Outcome::Cancelled;
            break;
        }
        if options
            .time_limit
            .is_some_and(|limit| start.elapsed() >= limit)
        {
            break;
        }
        solve_step(game, t);
        t += 1;
        if t % options.check_every == 0 || t == options.max_iterations {
            progress = Progress {
                iteration: t,
                exploitability: compute_exploitability(game) / pot,
                elapsed: start.elapsed(),
            };
            on_progress(progress);
        }
    }
    if outcome == Outcome::Exhausted && progress.exploitability <= options.target {
        outcome = Outcome::Converged;
    }
    finalize(game);
    (outcome, progress)
}

/// 从已解完的树里走到下一条街的开头（发完新牌、还没人行动）后，取出重新求解要用的局面：
/// 双方范围是走到这里的概率，底池和筹码按这条线上已下的注计算。
/// 会从根节点重放一遍历史，以便找出上一条街最后的进攻者。
pub fn next_street_spot(game: &mut PostFlopGame) -> Result<Spot, String> {
    if game.is_terminal_node() || game.is_chance_node() {
        return Err("当前不是决策节点".into());
    }
    let [oop, ip] = game.total_bet_amount();
    if oop != ip {
        return Err("还有未跟完的下注，不在一条街的开头".into());
    }
    let history = game.history().to_vec();
    game.back_to_root();
    let (mut street_aggressor, mut previous_aggressor) = (None, None);
    for &i in &history {
        if game.is_chance_node() {
            previous_aggressor = street_aggressor.take();
        } else if matches!(
            game.available_actions()[i],
            TreeAction::Bet(_) | TreeAction::Raise(_) | TreeAction::AllIn(_)
        ) {
            street_aggressor = Some(game.current_player());
        }
        game.play(i);
    }
    let config = game.tree_config();
    let pot = config.starting_pot + oop + ip;
    let stack = config.effective_stack - oop;
    let range =
        |player: usize| Range::from_hands_weights(game.private_cards(player), game.weights(player));
    Ok(Spot {
        board: game.current_board(),
        ranges: [range(0)?, range(1)?],
        pot: crate::to_bb(pot as f32),
        stack: crate::to_bb(stack as f32),
        oop_can_lead: previous_aggressor != Some(1),
    })
}
