use crate::line::{
    heads_up_seats, hole_cards, match_action, parse_cards, preflop_actions, street_moves,
};
use crate::types::{ActionAdvice, HandState, MoveKind, Progress, SolverStrategy};
use holdem::Card;
use postflop::{
    build_game, next_street_spot, range_from_classes, solve, to_chips, Outcome, Sizes,
    SolveOptions, Spot,
};
use postflop_solver::{Action as TreeAction, PostFlopGame, Range};
use preflop::{follow_line, load, Tree};
use std::collections::HashMap;
use std::fs::File;
use std::io::BufReader;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::time::Duration;

/// 玩家实际拿着的牌哪怕不在均衡范围里，也给一点点权重，这样它的策略和 EV 都有意义。
const HOLDING_FLOOR: f32 = 1e-3;

#[derive(Clone, Debug)]
pub struct EngineOptions {
    /// 可剥削度降到底池的这个比例以下就停。
    pub target: f32,
    /// 每条街最多求解多久，到时用当时的策略。
    pub time_limit: Duration,
    pub max_iterations: u32,
}

impl Default for EngineOptions {
    fn default() -> EngineOptions {
        EngineOptions {
            target: 0.003,
            time_limit: Duration::from_secs(120),
            max_iterations: 2000,
        }
    }
}

/// 求解引擎。可以在多个线程间共享（内部都是 Arc）。
#[derive(Clone)]
pub struct Engine {
    inner: Arc<Inner>,
}

struct Inner {
    dir: PathBuf,
    options: EngineOptions,
    tables: Mutex<HashMap<usize, Arc<Table>>>,
    solves: Mutex<HashMap<(String, usize), Arc<StreetSolve>>>,
}

struct Table {
    tree: Tree,
    strategy: Vec<f64>,
}

/// 一手牌某条街的求解：后台线程求解，完成后把博弈树放进 `state`。
struct StreetSolve {
    state: Mutex<SolveState>,
    ready: Condvar,
    cancel: AtomicBool,
}

#[derive(Default)]
struct SolveState {
    done: bool,
    game: Option<PostFlopGame>,
    error: Option<String>,
    exploitability: f32,
}

type ProgressFn = Arc<dyn Fn(Progress) + Send + Sync>;

impl Engine {
    /// `preflop_dir` 里放 `2max.bin` 到 `6max.bin`，用到时才读取。
    pub fn new(preflop_dir: &Path, options: EngineOptions) -> Engine {
        Engine {
            inner: Arc::new(Inner {
                dir: preflop_dir.to_path_buf(),
                options,
                tables: Mutex::new(HashMap::new()),
                solves: Mutex::new(HashMap::new()),
            }),
        }
    }

    /// 当前局面能否用求解器：翻牌开始就是两人底池，且翻前没有全下。
    pub fn supports(&self, state: &HandState) -> bool {
        if !(3..=5).contains(&state.board.len()) {
            return false;
        }
        let Ok(table) = self.table(state.players) else {
            return false;
        };
        preflop_actions(&table.tree, &state.preflop)
            .ok()
            .and_then(|path| heads_up_seats(&table.tree, &path))
            .is_some()
    }

    /// 开始（或复用）当前这条街的后台求解，立即返回。同一手牌同一条街只求解一次。
    pub fn prepare(
        &self,
        state: &HandState,
        on_progress: impl Fn(Progress) + Send + Sync + 'static,
    ) -> Result<(), String> {
        self.start(state, Arc::new(on_progress)).map(|_| ())
    }

    /// 等这条街求解完，返回 `seat` 用自己的实际手牌在当前节点的策略。
    pub fn strategy(&self, state: &HandState, seat: usize) -> Result<SolverStrategy, String> {
        let solve = self.start(state, Arc::new(|_| {}))?;
        let street = street_of(state)?;
        let table = self.table(state.players)?;
        let path = preflop_actions(&table.tree, &state.preflop)?;
        let seats = heads_up_seats(&table.tree, &path).ok_or("不是两人底池")?;
        let player = seats
            .iter()
            .position(|&s| s == seat)
            .ok_or("这个座位不在底池里")?;
        let hand = hole_cards(state, seat)?;

        let mut guard = wait(&solve)?;
        let exploitability = guard.exploitability;
        let game = guard.game.as_mut().ok_or("求解结果缺失")?;
        game.back_to_root();
        replay(game, state, street, &seats)?;
        if game.is_terminal_node() || game.is_chance_node() {
            return Err("这条街已经没有人需要行动".into());
        }
        if game.current_player() != player {
            return Err("现在不是这个座位行动".into());
        }
        let index = game
            .private_cards(player)
            .iter()
            .position(|&h| h == hand)
            .ok_or("手牌不在求解范围里")?;
        game.cache_normalized_weights();
        let n = game.private_cards(player).len();
        let strategy = game.strategy();
        let evs = game.expected_values_detail(player);
        let bets = game.total_bet_amount();
        let actions = game
            .available_actions()
            .iter()
            .enumerate()
            .map(|(k, &a)| {
                let (kind, to) = match a {
                    TreeAction::Fold => (MoveKind::Fold, bets[player]),
                    TreeAction::Check => (MoveKind::Check, bets[player]),
                    TreeAction::Call => (MoveKind::Call, bets[player ^ 1]),
                    TreeAction::Bet(x) => (MoveKind::Bet, x),
                    TreeAction::Raise(x) => (MoveKind::Raise, x),
                    TreeAction::AllIn(x) => (MoveKind::Allin, x),
                    _ => unreachable!("决策节点不会有发牌动作"),
                };
                ActionAdvice {
                    kind,
                    to: postflop::to_bb(to as f32),
                    freq: strategy[k * n + index],
                    ev: postflop::to_bb(evs[k * n + index]),
                }
            })
            .collect();
        Ok(SolverStrategy {
            actions,
            exploitability,
        })
    }

    /// 取消这手牌所有还在进行的求解（比如玩家已经弃牌或开始下一手）。
    pub fn cancel(&self, hand_id: &str) {
        let mut solves = self.inner.solves.lock().unwrap();
        solves.retain(|(id, _), solve| {
            if id == hand_id {
                solve.cancel.store(true, Ordering::Relaxed);
                false
            } else {
                true
            }
        });
    }

    fn table(&self, players: usize) -> Result<Arc<Table>, String> {
        let mut tables = self.inner.tables.lock().unwrap();
        if let Some(t) = tables.get(&players) {
            return Ok(t.clone());
        }
        let path = self.inner.dir.join(format!("{players}max.bin"));
        let file = File::open(&path).map_err(|e| format!("读取 {}：{e}", path.display()))?;
        let (config, strategy, _) =
            load(BufReader::new(file)).map_err(|e| format!("读取 {}：{e}", path.display()))?;
        let table = Arc::new(Table {
            tree: Tree::build(config),
            strategy,
        });
        tables.insert(players, table.clone());
        Ok(table)
    }

    fn start(
        &self,
        state: &HandState,
        on_progress: ProgressFn,
    ) -> Result<Arc<StreetSolve>, String> {
        let street = street_of(state)?;
        let key = (state.hand_id.clone(), street);
        {
            let solves = self.inner.solves.lock().unwrap();
            if let Some(solve) = solves.get(&key) {
                return Ok(solve.clone());
            }
        }
        if !self.supports(state) {
            return Err("只支持从翻牌开始的两人底池".into());
        }
        // 转牌和河牌要用上一条街的结果，先确保它已经开始。
        let previous = if street > 1 {
            let mut earlier = state.clone();
            earlier.board.truncate(street + 1);
            earlier.postflop.retain(|m| m.street < street);
            Some(self.start(&earlier, Arc::new(|_| {}))?)
        } else {
            None
        };
        let solve = Arc::new(StreetSolve {
            state: Mutex::new(SolveState::default()),
            ready: Condvar::new(),
            cancel: AtomicBool::new(false),
        });
        {
            let mut solves = self.inner.solves.lock().unwrap();
            if let Some(existing) = solves.get(&key) {
                return Ok(existing.clone());
            }
            solves.insert(key, solve.clone());
        }
        let engine = self.clone();
        let state = state.clone();
        let worker = solve.clone();
        std::thread::spawn(move || {
            let result = engine.run(&state, street, previous, &worker, on_progress);
            let mut guard = worker.state.lock().unwrap();
            match result {
                Ok((game, exploitability)) => {
                    guard.game = Some(game);
                    guard.exploitability = exploitability;
                }
                Err(e) => guard.error = Some(e),
            }
            guard.done = true;
            worker.ready.notify_all();
        });
        Ok(solve)
    }

    fn run(
        &self,
        state: &HandState,
        street: usize,
        previous: Option<Arc<StreetSolve>>,
        solve_slot: &StreetSolve,
        on_progress: ProgressFn,
    ) -> Result<(PostFlopGame, f32), String> {
        let table = self.table(state.players)?;
        let path = preflop_actions(&table.tree, &state.preflop)?;
        let seats = heads_up_seats(&table.tree, &path).ok_or("不是两人底池")?;
        let board = parse_cards(&state.board)?;

        let mut spot = match previous {
            None => {
                let line = follow_line(&table.tree, &table.strategy, &path)
                    .ok_or("翻前行动线不在范围表里")?;
                let stack = table.tree.config.stack - line.contrib[seats[0]];
                Spot {
                    board: board.clone(),
                    ranges: [
                        range_from_classes(&line.ranges[seats[0]]),
                        range_from_classes(&line.ranges[seats[1]]),
                    ],
                    pot: line.contrib.iter().sum(),
                    stack,
                }
            }
            Some(previous) => {
                let mut guard = wait(&previous)?;
                let game = guard.game.as_mut().ok_or("上一条街没有求解结果")?;
                game.back_to_root();
                replay(game, state, street - 1, &seats)?;
                if !game.is_chance_node() {
                    return Err("上一条街还没结束".into());
                }
                game.play(board[street + 1] as usize);
                let spot = next_street_spot(game)?;
                game.back_to_root();
                spot
            }
        };
        for (player, &seat) in seats.iter().enumerate() {
            floor_holding(&mut spot.ranges[player], hole_cards(state, seat)?);
        }

        let options = &self.inner.options;
        let mut game = build_game(&spot, &Sizes::precise(board.len()), false)?;
        let solve_options = SolveOptions {
            target: options.target,
            max_iterations: options.max_iterations,
            check_every: 10,
            time_limit: Some(options.time_limit),
        };
        let mut initial = None;
        let hand_id = state.hand_id.clone();
        let (outcome, last) = solve(&mut game, &solve_options, &solve_slot.cancel, |p| {
            let e0 = *initial.get_or_insert(p.exploitability);
            on_progress(Progress {
                hand_id: hand_id.clone(),
                street,
                iteration: p.iteration,
                exploitability: p.exploitability,
                fraction: fraction(e0, p.exploitability, options.target),
                done: false,
            });
        });
        if outcome == Outcome::Cancelled {
            return Err("求解已取消".into());
        }
        on_progress(Progress {
            hand_id,
            street,
            iteration: last.iteration,
            exploitability: last.exploitability,
            fraction: 1.0,
            done: true,
        });
        Ok((game, last.exploitability))
    }
}

/// 公共牌张数换成街：3 张是翻牌（1），4 张转牌（2），5 张河牌（3）。
fn street_of(state: &HandState) -> Result<usize, String> {
    match state.board.len() {
        3..=5 => Ok(state.board.len() - 2),
        n => Err(format!("公共牌应为 3 到 5 张，实际 {n} 张")),
    }
}

fn wait(solve: &StreetSolve) -> Result<std::sync::MutexGuard<'_, SolveState>, String> {
    let mut guard = solve.state.lock().unwrap();
    while !guard.done {
        guard = solve.ready.wait(guard).unwrap();
    }
    if let Some(e) = &guard.error {
        return Err(e.clone());
    }
    Ok(guard)
}

/// 从这条街的根节点开始，按前端记录的动作走到当前节点。
fn replay(
    game: &mut PostFlopGame,
    state: &HandState,
    street: usize,
    seats: &[usize; 2],
) -> Result<(), String> {
    for m in street_moves(state, street) {
        if game.is_terminal_node() || game.is_chance_node() {
            return Err("动作比求解树里的多".into());
        }
        let player = seats
            .iter()
            .position(|&s| s == m.seat)
            .ok_or("动作来自不在底池里的座位")?;
        if game.current_player() != player {
            return Err("动作顺序和求解树不一致".into());
        }
        let actions = game.available_actions();
        let k = match_action(&actions, m.kind, to_chips(m.to))
            .ok_or_else(|| format!("求解树里没有对应的动作：{:?} {}", m.kind, m.to))?;
        game.play(k);
    }
    Ok(())
}

fn floor_holding(range: &mut Range, (a, b): (Card, Card)) {
    if range.get_weight_by_cards(a, b) < HOLDING_FLOOR {
        range.set_weight_by_cards(a, b, HOLDING_FLOOR);
    }
}

/// 可剥削度从 e0 降到 target，按对数比例换算成进度。
fn fraction(e0: f32, e: f32, target: f32) -> f32 {
    if e <= target || e0 <= target {
        return 1.0;
    }
    ((e0 / e).ln() / (e0 / target).ln()).clamp(0.0, 1.0)
}
