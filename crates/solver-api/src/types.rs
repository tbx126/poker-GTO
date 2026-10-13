use serde::{Deserialize, Serialize};

/// 一手牌当前的状态，字段和前端 `GameState` 对应，前端可以直接从它构造。
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct HandState {
    /// 这手牌的唯一编号，用来缓存求解结果。
    pub hand_id: String,
    pub players: usize,
    /// 翻前历史，和范围表 JSON 的 history 相同，例如 `["UTG 弃牌", "BTN 加注到 2.5"]`。
    pub preflop: Vec<String>,
    /// 公共牌，例如 `["Td", "9d", "6h"]`。
    pub board: Vec<String>,
    /// 翻后每个动作，按发生顺序。
    pub postflop: Vec<PostflopMove>,
    /// 每个座位的两张底牌，按座位号。
    pub cards: Vec<[String; 2]>,
}

/// 翻后的一个动作。`to` 是动作之后这条街的总投入（bb），和前端 `Move.to` 相同。
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PostflopMove {
    /// 1 翻牌，2 转牌，3 河牌。
    pub street: usize,
    pub seat: usize,
    pub kind: MoveKind,
    pub to: f32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum MoveKind {
    Fold,
    Check,
    Call,
    Bet,
    Raise,
    Allin,
}

/// 求解进度，前端用来画进度条。
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Progress {
    pub hand_id: String,
    pub street: usize,
    pub iteration: u32,
    /// 可剥削度占这条街起始底池的比例。
    pub exploitability: f32,
    /// 0 到 1，按可剥削度从初始值降到目标值的对数比例估算。
    pub fraction: f32,
    pub done: bool,
    /// 结束时是否达到了目标精度；为 false 表示是到了时间或轮数上限才停的。
    pub converged: bool,
}

/// 某个座位在当前节点的策略。
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SolverStrategy {
    pub actions: Vec<ActionAdvice>,
    /// 这条街求解结束时的可剥削度（占底池比例）。
    pub exploitability: f32,
    /// 是否达到了目标精度；为 false 表示到了时间或轮数上限，策略只是近似。
    pub converged: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ActionAdvice {
    pub kind: MoveKind,
    /// 动作之后这条街的总投入（bb）。
    pub to: f32,
    /// GTO 频率，0 到 1。
    pub freq: f32,
    /// 相对“现在弃牌”的期望收益（bb），弃牌为 0。
    pub ev: f32,
}

/// 前端算出的一个合法动作，规则近似只评估这些动作。
#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LegalMove {
    pub kind: MoveKind,
    /// 动作之后这条街的总投入（bb）。
    pub to: f32,
}

/// 多人底池的规则近似策略，不是求解结果，界面上要标“近似”。
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ApproxStrategy {
    pub actions: Vec<ActionAdvice>,
    /// 主角对各对手（按动作收窄后的）范围摊牌的胜率。
    pub equity: f32,
}
