use holdem::{EquityTable, HandClass, NUM_CLASSES};

const N: usize = NUM_CLASSES;

/// 实现率参数：一手牌翻后能把多少全下胜率变成实际收益。
///
/// 实现率 = 位置基准 + 斜率 × (这手牌对随机手牌的胜率 - 0.5) + 同花加成。
/// 强牌和有位置的一方实现得多，弱牌和没位置的一方实现得少。
#[derive(Clone, Copy, Debug)]
pub struct Realization {
    pub ip: f64,
    pub oop: f64,
    pub slope: f64,
    pub suited_bonus: f64,
}

impl Default for Realization {
    fn default() -> Self {
        Realization {
            // 按 4 人桌开池范围和大盲防守频率与公开 GTO 结果大致吻合来选定。
            ip: 1.0,
            oop: 0.85,
            slope: 1.25,
            suited_bonus: 0.03,
        }
    }
}

/// 翻前结束、还有两人以上没弃牌时，用来估算每个人能分到多少底池的模型。
///
/// - 全下：按全下胜率分底池。
/// - 两人底池：每一对具体手牌按 `胜率 × 实现率` 重新归一化，
///   保证两人份额之和等于底池。实现率见 [`Realization`]。
/// - 多人底池：用两两份额的乘积近似独赢整个底池的概率，近似误差平分给所有人，
///   保证每组手牌的份额之和等于底池（详见 `solver::pot_share`）。
///
/// 这是对翻后博弈的近似，忽略了牌的阻挡效应（card removal）。
pub struct Model {
    /// 全下胜率矩阵 M[h][x]：手牌 h 对 x 的胜率。
    pub equity: Vec<f64>,
    /// 有位置一方的份额矩阵。
    pub share_ip: Vec<f64>,
    /// 没位置一方的份额矩阵，满足 share_oop[x][h] = 1 - share_ip[h][x]。
    pub share_oop: Vec<f64>,
    pub realization: Realization,
}

impl Model {
    pub fn new(table: &EquityTable, realization: Realization) -> Model {
        let equity: Vec<f64> = table.as_slice().iter().map(|&v| v as f64).collect();
        // 每手牌对随机手牌的胜率（按对手组合数加权）。
        let weights: Vec<f64> = HandClass::all().map(|h| h.num_combos() as f64).collect();
        let total: f64 = weights.iter().sum();
        let factor = |h: HandClass, base: f64| {
            let row = &equity[h.index() * N..(h.index() + 1) * N];
            let vs_random: f64 = row.iter().zip(&weights).map(|(m, w)| m * w).sum::<f64>() / total;
            let bonus = if h.is_suited() {
                realization.suited_bonus
            } else {
                0.0
            };
            (base + realization.slope * (vs_random - 0.5) + bonus).max(0.05)
        };
        let r_ip: Vec<f64> = HandClass::all()
            .map(|h| factor(h, realization.ip))
            .collect();
        let r_oop: Vec<f64> = HandClass::all()
            .map(|h| factor(h, realization.oop))
            .collect();
        // K[h][x] = M·R_p(h) / (M·R_p(h) + (1 - M)·R_o(x))
        let share = |mine: &[f64], theirs: &[f64]| -> Vec<f64> {
            (0..N * N)
                .map(|i| {
                    let (h, x) = (i / N, i % N);
                    let a = equity[i] * mine[h];
                    let b = (1.0 - equity[i]) * theirs[x];
                    if a + b > 0.0 {
                        a / (a + b)
                    } else {
                        0.5
                    }
                })
                .collect()
        };
        Model {
            share_ip: share(&r_ip, &r_oop),
            share_oop: share(&r_oop, &r_ip),
            equity,
            realization,
        }
    }

    /// 从仓库自带的胜率表加载，使用默认实现率。
    pub fn load_default() -> std::io::Result<Model> {
        Model::load(Realization::default())
    }

    pub fn load(realization: Realization) -> std::io::Result<Model> {
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../data/equity_hu_169.bin");
        let table = EquityTable::read_from(std::io::BufReader::new(std::fs::File::open(path)?))?;
        Ok(Model::new(&table, realization))
    }
}

/// out[h] = Σ_x matrix[h][x] · v[x]
pub fn mat_vec(matrix: &[f64], v: &[f64], out: &mut [f64]) {
    for (h, o) in out.iter_mut().enumerate() {
        let row = &matrix[h * N..(h + 1) * N];
        *o = row.iter().zip(v).map(|(m, x)| m * x).sum();
    }
}
