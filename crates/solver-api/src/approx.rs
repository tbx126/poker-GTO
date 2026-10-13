//! 多人底池的规则近似：不求解，按对手的实际动作收窄他们的范围，再用蒙特卡洛估算每个动作的 EV。
//!
//! 1. 每个对手的起始范围来自翻前范围表走到这条行动线的结果。
//! 2. 每条街按对手的动作收窄：下注、加注保留强牌和一部分最弱的牌（诈唬），
//!    跟注保留中等以上，过牌削掉最强的一截。“强弱”是这手牌在该对手当前范围里的分位，
//!    牌力用对随机一手牌的胜率衡量，这样听牌也算有一定强度。
//! 3. 主动投注时，每个对手按底池赔率弃掉范围里最弱的一部分（合起来全弃的概率等于底池赔率），
//!    剩下的跟注；在同一批模拟里抽对手手牌和后面的公共牌，直接算出这个动作的平均收益。
//! 4. 按 EV 做 softmax 得到频率，和前端的近似一致。

use crate::line::{hole_cards, parse_cards, preflop_actions, street_moves};
use crate::types::{ActionAdvice, HandState, LegalMove, MoveKind};
use holdem::{evaluate, Card, HandClass, HandRank, Rng};
use preflop::{follow_line, Tree};

/// 每个组合算牌力时的模拟次数。
const STRENGTH_SAMPLES: usize = 160;
/// 每个动作算 EV 时的模拟次数。
const EV_SAMPLES: usize = 4000;
/// 对手防守比最低防守频率宽出的比例。
const EXTRA_DEFENSE: f32 = 0.15;
/// 对手合起来至少防守这么多，超池全下时不会几乎全弃。
const MIN_DEFENSE: f32 = 0.2;
/// 后面的街按每条街一个底池的下注算，最多还能进多少钱（以现在底池为单位）：剩一条街 1 倍，剩两条街 3 倍。
const FUTURE_POTS: [f32; 3] = [0.0, 1.0, 3.0];
/// 领先时这些将来的钱里预计能赢到的比例。
const IMPLIED_SHARE: f32 = 0.4;

/// 52 张牌的全部 1326 个组合，按 (a, b)，a < b。
fn combos() -> Vec<(Card, Card)> {
    let mut v = Vec::with_capacity(1326);
    for a in 0..52u8 {
        for b in a + 1..52 {
            v.push((a, b));
        }
    }
    v
}

fn mask(cards: &[Card]) -> u64 {
    cards.iter().fold(0, |m, &c| m | 1 << c)
}

fn bit2(a: Card, b: Card) -> u64 {
    1 << a | 1 << b
}

pub(crate) struct Approx {
    pub actions: Vec<ActionAdvice>,
    pub equity: f32,
}

/// 一个还在底池里的对手。
struct Opponent {
    seat: usize,
    /// 每个组合的权重，和 `combos()` 对齐。
    weights: Vec<f64>,
    /// 这条街已投入（bb）。
    street: f32,
    /// 剩余筹码（bb）。
    stack: f32,
}

pub(crate) fn approx(
    tree: &Tree,
    strategy: &[f64],
    state: &HandState,
    seat: usize,
    legal: &[LegalMove],
) -> Result<Approx, String> {
    let street = match state.board.len() {
        3..=5 => state.board.len() - 2,
        n => return Err(format!("公共牌应为 3 到 5 张，实际 {n} 张")),
    };
    let board = parse_cards(&state.board)?;
    let hero = hole_cards(state, seat)?;
    let path = preflop_actions(tree, &state.preflop)?;
    let line = follow_line(tree, strategy, &path).ok_or("翻前行动线不在范围表里")?;
    if line.alive.is_empty() {
        return Err("翻前还没结束".into());
    }
    if !line.alive.contains(&seat) {
        return Err("这个座位翻前已经弃牌".into());
    }
    let config = &tree.config;
    let all = combos();
    let mut seed = state
        .hand_id
        .bytes()
        .fold(0xcbf2_9ce4_8422_2325u64, |h, b| {
            (h ^ b as u64).wrapping_mul(0x100_0000_01b3)
        });
    seed ^= (street as u64) << 56 | (seat as u64) << 48;
    let mut rng = Rng::new(seed);

    let mut committed = line.contrib.clone();
    let mut folded: Vec<bool> = (0..config.players)
        .map(|s| !line.alive.contains(&s))
        .collect();
    let hero_mask = bit2(hero.0, hero.1);
    let mut opponents: Vec<Opponent> = line
        .alive
        .iter()
        .filter(|&&s| s != seat)
        .map(|&s| Opponent {
            seat: s,
            weights: all
                .iter()
                .map(|&(a, b)| {
                    if bit2(a, b) & hero_mask != 0 {
                        0.0
                    } else {
                        line.ranges[s][HandClass::of_cards(a, b).index()]
                    }
                })
                .collect(),
            street: 0.0,
            stack: 0.0,
        })
        .collect();

    // 一条街一条街地按对手的动作收窄范围，同时记下底池。
    let mut street_bets = vec![0.0f32; config.players];
    for s in 1..=street {
        let cards = &board[..s + 2];
        let dead = mask(cards);
        let strength = strengths(&all, cards, &mut rng);
        for o in &mut opponents {
            for (w, &(a, b)) in o.weights.iter_mut().zip(&all) {
                if bit2(a, b) & dead != 0 {
                    *w = 0.0;
                }
            }
        }
        street_bets.iter_mut().for_each(|b| *b = 0.0);
        for m in street_moves(state, s) {
            let bet = street_bets.iter().cloned().fold(0.0, f32::max);
            let pot: f32 = committed.iter().sum();
            let alive_after = (0..config.players).filter(|&i| !folded[i]).count();
            if let Some(o) = opponents.iter_mut().find(|o| o.seat == m.seat) {
                let q: Vec<f64> = percentiles(&o.weights, &strength)
                    .iter()
                    .map(|&(lo, hi)| (lo + hi) / 2.0)
                    .collect();
                let to_call = bet - street_bets[m.seat];
                let likelihood: Box<dyn Fn(f64) -> f64> = match m.kind {
                    MoveKind::Fold => Box::new(|_| 1.0),
                    MoveKind::Check => Box::new(check_likelihood),
                    MoveKind::Call => {
                        // 要跟的钱占（含下注的）底池的比例，就是诈唬不亏所需的弃牌率。
                        let alpha = (to_call / pot.max(0.5)).clamp(0.0, 0.95) as f64;
                        // 面对下注的还有几个人：越多，每个人防守得越紧。
                        let k = (alive_after - 1).max(1) as f64;
                        Box::new(move |q| call_likelihood(q, alpha.powf(1.0 / k)))
                    }
                    MoveKind::Bet | MoveKind::Raise | MoveKind::Allin => {
                        let size = (m.to - bet).max(0.0) / (pot + to_call).max(0.5);
                        let raise = bet > 0.0;
                        Box::new(move |q| aggressive_likelihood(q, size as f64, raise))
                    }
                };
                for (w, q) in o.weights.iter_mut().zip(q) {
                    *w *= likelihood(q);
                }
            }
            if m.kind == MoveKind::Fold {
                folded[m.seat] = true;
            }
            let added = (m.to - street_bets[m.seat]).max(0.0);
            committed[m.seat] += added;
            street_bets[m.seat] += added;
        }
    }
    opponents.retain(|o| !folded[o.seat]);
    if opponents.is_empty() {
        return Err("已经没有对手".into());
    }
    for o in &mut opponents {
        o.street = street_bets[o.seat];
        o.stack = config.stack - committed[o.seat];
    }

    let pot: f32 = committed.iter().sum();
    let mine = street_bets[seat];
    let hero_stack = config.stack - committed[seat];
    let last_to_act = opponents
        .iter()
        .all(|o| config.postflop_order(o.seat) < config.postflop_order(seat));
    let realization = if street == 3 {
        1.0
    } else if last_to_act {
        0.95
    } else {
        0.8
    };

    let strength = strengths(&all, &board, &mut rng);
    let samplers: Vec<Sampler> = opponents.iter().map(|o| Sampler::new(&o.weights)).collect();
    let equity = showdown_equity(&all, &board, hero, &samplers, &mut rng);

    let k = opponents.len() as f64;
    let thresholds: Vec<Vec<(f64, f64)>> = opponents
        .iter()
        .map(|o| percentiles(&o.weights, &strength))
        .collect();
    // 后面的街还能再下注：领先时多赢一些（落后可以弃牌，不算反向的损失）。
    let future = FUTURE_POTS[3 - street];
    let deepest = opponents.iter().map(|o| o.stack).fold(0.0, f32::max);
    let implied = |share: f32, pot_after: f32, stack_after: f32| {
        let room = stack_after.min(deepest).min(pot_after * future).max(0.0);
        (2.0 * share - 1.0).max(0.0) * room * IMPLIED_SHARE
    };
    let mut actions: Vec<ActionAdvice> = legal
        .iter()
        .map(|m| {
            let added = (m.to - mine).max(0.0);
            let ev = match m.kind {
                MoveKind::Fold => 0.0,
                MoveKind::Check => equity * pot * realization + implied(equity, pot, hero_stack),
                MoveKind::Call => {
                    if hero_stack <= added {
                        equity * (pot + added) - added
                    } else {
                        equity * (pot + added) * realization - added
                            + implied(equity, pot + added, hero_stack - added)
                    }
                }
                MoveKind::Bet | MoveKind::Raise | MoveKind::Allin => {
                    let r = if m.kind == MoveKind::Allin {
                        1.0
                    } else {
                        realization
                    };
                    // 每个对手要补的钱，以及他弃牌的阈值（范围里最弱的这部分弃牌）。
                    // 对手合起来的防守频率比最低防守频率 pot / (pot + added) 宽一点，
                    // 这样纯诈唬会亏掉底池的 EXTRA_DEFENSE（超池时更多），不至于到处诈唬。
                    let defend =
                        (pot / (pot + added) * (1.0 + EXTRA_DEFENSE)).clamp(MIN_DEFENSE, 0.98);
                    let alpha = (1.0 - defend).max(0.0) as f64;
                    let calls: Vec<(f32, f64)> = opponents
                        .iter()
                        .map(|o| {
                            let x = (m.to.min(o.street + o.stack) - o.street).max(0.0);
                            (x, alpha.powf(1.0 / k))
                        })
                        .collect();
                    let called = bet_ev(
                        &all,
                        &board,
                        hero,
                        &samplers,
                        &thresholds,
                        &calls,
                        pot + added,
                        added,
                        r,
                        &mut rng,
                    );
                    let mut ev = called.ev;
                    if m.kind != MoveKind::Allin {
                        ev += called.called * implied(called.share, called.pot, hero_stack - added);
                    }
                    ev
                }
            };
            ActionAdvice {
                kind: m.kind,
                to: m.to,
                freq: 0.0,
                ev: (ev * 100.0).round() / 100.0,
            }
        })
        .collect();

    // 和前端近似相同：EV 越接近最好的动作，频率越高，底池越大混合越少。
    let best = actions.iter().map(|a| a.ev).fold(f32::MIN, f32::max);
    let temperature = (0.04 * pot).max(0.08);
    for a in &mut actions {
        a.freq = ((a.ev - best) / temperature).exp();
    }
    normalize(&mut actions);
    for a in &mut actions {
        if a.freq < 0.02 {
            a.freq = 0.0;
        }
    }
    normalize(&mut actions);
    Ok(Approx { actions, equity })
}

fn normalize(actions: &mut [ActionAdvice]) {
    let total: f32 = actions.iter().map(|a| a.freq).sum();
    if total > 0.0 {
        for a in actions {
            a.freq /= total;
        }
    }
}

fn sigmoid(x: f64) -> f64 {
    1.0 / (1.0 + (-x).exp())
}

/// 过牌：最强的一截大多会下注，所以过牌范围被削顶，但不完全去掉（慢打）。
fn check_likelihood(q: f64) -> f64 {
    1.0 - 0.75 * sigmoid((q - 0.85) / 0.04)
}

/// 跟注：范围里最弱的 `fold` 比例弃牌，最强的一小截多半会加注。
fn call_likelihood(q: f64, fold: f64) -> f64 {
    sigmoid((q - fold) / 0.05) * (1.0 - 0.6 * sigmoid((q - 0.95) / 0.02))
}

/// 下注或加注：价值部分是范围的顶端，尺寸越大越极化；
/// 诈唬取自范围最弱的 35%，占投注范围的比例按尺寸算（下注 b 倍底池时为 b / (1 + 2b)）。
fn aggressive_likelihood(q: f64, size: f64, raise: bool) -> f64 {
    let value = if raise {
        0.12
    } else {
        0.35 - 0.1 * size.min(1.5)
    };
    let bluff_share = size / (1.0 + 2.0 * size);
    let bluff = (value * bluff_share / (1.0 - bluff_share) / 0.35).min(1.0);
    let v = sigmoid((q - (1.0 - value)) / 0.04);
    let b = bluff * sigmoid((0.35 - q) / 0.04);
    (v + b).min(1.0)
}

/// 每个组合在这些公共牌上对一手随机牌的胜率（平局算一半），和公共牌冲突的为 0。
fn strengths(all: &[(Card, Card)], board: &[Card], rng: &mut Rng) -> Vec<f64> {
    let dead = mask(board);
    let seed = rng.next_u64();
    let threads = std::thread::available_parallelism().map_or(4, |n| n.get());
    let chunk = all.len().div_ceil(threads);
    let mut out = vec![0.0; all.len()];
    std::thread::scope(|scope| {
        for (t, (part, combos)) in out.chunks_mut(chunk).zip(all.chunks(chunk)).enumerate() {
            scope.spawn(move || {
                let mut rng = Rng::new(seed ^ (t as u64 + 1).wrapping_mul(0x9E37_79B9_7F4A_7C15));
                let mut cards = [0u8; 7];
                for (s, &(a, b)) in part.iter_mut().zip(combos) {
                    let used = dead | bit2(a, b);
                    if dead & bit2(a, b) != 0 {
                        continue;
                    }
                    let mut won = 0.0;
                    for _ in 0..STRENGTH_SAMPLES {
                        let mut taken = used;
                        let mut draw = || loop {
                            let c = rng.below(52) as Card;
                            if taken & 1 << c == 0 {
                                taken |= 1 << c;
                                return c;
                            }
                        };
                        let (c, d) = (draw(), draw());
                        let n = board.len();
                        cards[..n].copy_from_slice(board);
                        for slot in cards.iter_mut().take(5).skip(n) {
                            *slot = draw();
                        }
                        cards[5] = a;
                        cards[6] = b;
                        let mine = evaluate(&cards);
                        cards[5] = c;
                        cards[6] = d;
                        let theirs = evaluate(&cards);
                        won += match mine.cmp(&theirs) {
                            std::cmp::Ordering::Greater => 1.0,
                            std::cmp::Ordering::Equal => 0.5,
                            std::cmp::Ordering::Less => 0.0,
                        };
                    }
                    *s = won / STRENGTH_SAMPLES as f64;
                }
            });
        }
    });
    out
}

/// 每个组合在这份范围里的分位区间（0 最弱，1 最强），按权重算。
/// 牌力相同的组合共用一个区间，用的时候在区间里随机取点，阈值落在一批同样强的牌中间时也能按比例分开。
fn percentiles(weights: &[f64], strength: &[f64]) -> Vec<(f64, f64)> {
    let mut order: Vec<usize> = (0..weights.len()).filter(|&i| weights[i] > 0.0).collect();
    order.sort_by(|&i, &j| strength[i].total_cmp(&strength[j]));
    let total: f64 = order.iter().map(|&i| weights[i]).sum();
    let mut q = vec![(0.0, 0.0); weights.len()];
    if total <= 0.0 {
        return q;
    }
    let mut i = 0;
    let mut below = 0.0;
    while i < order.len() {
        let mut j = i;
        let mut mass = 0.0;
        while j < order.len() && strength[order[j]] == strength[order[i]] {
            mass += weights[order[j]];
            j += 1;
        }
        let span = (below / total, (below + mass) / total);
        for &h in &order[i..j] {
            q[h] = span;
        }
        below += mass;
        i = j;
    }
    q
}

/// 按权重抽组合（累积权重上二分）。
struct Sampler {
    cumulative: Vec<f64>,
    index: Vec<usize>,
}

impl Sampler {
    fn new(weights: &[f64]) -> Sampler {
        let mut cumulative = Vec::new();
        let mut index = Vec::new();
        let mut sum = 0.0;
        for (i, &w) in weights.iter().enumerate() {
            if w > 0.0 {
                sum += w;
                cumulative.push(sum);
                index.push(i);
            }
        }
        Sampler { cumulative, index }
    }

    fn sample(&self, rng: &mut Rng) -> Option<usize> {
        let total = *self.cumulative.last()?;
        let x = (rng.next_u64() >> 11) as f64 / (1u64 << 53) as f64 * total;
        let k = self.cumulative.partition_point(|&c| c <= x);
        Some(self.index[k.min(self.index.len() - 1)])
    }
}

/// 抽一组互不冲突的对手手牌，再把公共牌发完。抽不出来（范围被堵死）时返回 None。
fn deal(
    all: &[(Card, Card)],
    board: &[Card],
    hero: (Card, Card),
    samplers: &[Sampler],
    rng: &mut Rng,
    hands: &mut Vec<usize>,
    runout: &mut [Card; 5],
) -> Option<()> {
    'retry: for _ in 0..64 {
        let mut used = mask(board) | bit2(hero.0, hero.1);
        hands.clear();
        for s in samplers {
            let h = s.sample(rng)?;
            let (a, b) = all[h];
            if used & bit2(a, b) != 0 {
                continue 'retry;
            }
            used |= bit2(a, b);
            hands.push(h);
        }
        runout[..board.len()].copy_from_slice(board);
        for slot in runout.iter_mut().skip(board.len()) {
            let c = loop {
                let c = rng.below(52) as Card;
                if used & 1 << c == 0 {
                    break c;
                }
            };
            used |= 1 << c;
            *slot = c;
        }
        return Some(());
    }
    None
}

fn rank_of(runout: &[Card; 5], (a, b): (Card, Card)) -> HandRank {
    let mut cards = [0u8; 7];
    cards[..5].copy_from_slice(runout);
    cards[5] = a;
    cards[6] = b;
    evaluate(&cards)
}

/// 主角对所有对手当前范围摊牌的胜率（平分按份额）。
fn showdown_equity(
    all: &[(Card, Card)],
    board: &[Card],
    hero: (Card, Card),
    samplers: &[Sampler],
    rng: &mut Rng,
) -> f32 {
    let (mut won, mut n) = (0.0, 0);
    let mut hands = Vec::new();
    let mut runout = [0u8; 5];
    for _ in 0..EV_SAMPLES {
        if deal(all, board, hero, samplers, rng, &mut hands, &mut runout).is_none() {
            continue;
        }
        let mine = rank_of(&runout, hero);
        let ranks: Vec<HandRank> = hands.iter().map(|&h| rank_of(&runout, all[h])).collect();
        won += share(mine, &ranks);
        n += 1;
    }
    if n == 0 {
        0.5
    } else {
        (won / n as f64) as f32
    }
}

/// 主角赢得的份额：输给任何人为 0，和 t 个人打平为 1 / (t + 1)。
fn share(mine: HandRank, others: &[HandRank]) -> f64 {
    let mut ties = 0;
    for &r in others {
        if r > mine {
            return 0.0;
        }
        if r == mine {
            ties += 1;
        }
    }
    1.0 / (ties + 1) as f64
}

struct BetOutcome {
    /// 平均收益（相对现在弃牌），不含后面街的额外收益。
    ev: f32,
    /// 至少有一人跟注的概率。
    called: f32,
    /// 被跟注时主角的平均份额和最终底池。
    share: f32,
    pot: f32,
}

/// 主动投注的结果。`pot` 已含主角这次投入的 `added`。
#[allow(clippy::too_many_arguments)]
fn bet_ev(
    all: &[(Card, Card)],
    board: &[Card],
    hero: (Card, Card),
    samplers: &[Sampler],
    percentiles: &[Vec<(f64, f64)>],
    calls: &[(f32, f64)],
    pot: f32,
    added: f32,
    realization: f32,
    rng: &mut Rng,
) -> BetOutcome {
    let (mut total, mut n) = (0.0f64, 0);
    let (mut called, mut shares, mut pots) = (0, 0.0f64, 0.0f64);
    let mut hands = Vec::new();
    let mut runout = [0u8; 5];
    let mut callers = Vec::new();
    for _ in 0..EV_SAMPLES {
        if deal(all, board, hero, samplers, rng, &mut hands, &mut runout).is_none() {
            continue;
        }
        n += 1;
        callers.clear();
        let mut final_pot = pot as f64;
        for (i, &h) in hands.iter().enumerate() {
            let (x, fold) = calls[i];
            let (lo, hi) = percentiles[i][h];
            let u = (rng.next_u64() >> 11) as f64 / (1u64 << 53) as f64;
            if lo + (hi - lo) * u >= fold {
                callers.push(h);
                final_pot += x as f64;
            }
        }
        if callers.is_empty() {
            // 所有人弃牌：赢下投注前的底池。
            total += (pot - added) as f64;
            continue;
        }
        let mine = rank_of(&runout, hero);
        let ranks: Vec<HandRank> = callers.iter().map(|&h| rank_of(&runout, all[h])).collect();
        let s = share(mine, &ranks);
        total += s * final_pot * realization as f64 - added as f64;
        called += 1;
        shares += s;
        pots += final_pot;
    }
    let per = |x: f64, d: usize| if d == 0 { 0.0 } else { (x / d as f64) as f32 };
    BetOutcome {
        ev: per(total, n),
        called: per(called as f64, n),
        share: per(shares, called),
        pot: per(pots, called),
    }
}
