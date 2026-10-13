use holdem::{EquityTable, NUM_CLASSES};

const N: usize = NUM_CLASSES;

/// 翻前结束、还有两人以上没弃牌时，用来估算每个人能分到多少底池的模型。
///
/// - 全下：按全下胜率分底池。
/// - 两人底池：按胜率分，但用“实现率”体现位置优势：
///   有位置一方实现率为 1，没位置一方为 `realization_oop`，
///   每一对具体手牌按 `胜率 × 实现率` 重新归一化，保证两人份额之和等于底池。
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
    pub realization_oop: f64,
}

impl Model {
    pub fn new(table: &EquityTable, realization_oop: f64) -> Model {
        let equity: Vec<f64> = table.as_slice().iter().map(|&v| v as f64).collect();
        let rho = realization_oop;
        let share_ip = equity.iter().map(|&m| m / (m + (1.0 - m) * rho)).collect();
        let share_oop = equity
            .iter()
            .map(|&m| m * rho / (m * rho + (1.0 - m)))
            .collect();
        Model {
            equity,
            share_ip,
            share_oop,
            realization_oop,
        }
    }

    /// 从仓库自带的胜率表加载，实现率默认 0.85。
    pub fn load_default() -> std::io::Result<Model> {
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../data/equity_hu_169.bin");
        let table = EquityTable::read_from(std::io::BufReader::new(std::fs::File::open(path)?))?;
        Ok(Model::new(&table, 0.85))
    }
}

/// out[h] = Σ_x matrix[h][x] · v[x]
pub fn mat_vec(matrix: &[f64], v: &[f64], out: &mut [f64]) {
    for (h, o) in out.iter_mut().enumerate() {
        let row = &matrix[h * N..(h + 1) * N];
        *o = row.iter().zip(v).map(|(m, x)| m * x).sum();
    }
}
