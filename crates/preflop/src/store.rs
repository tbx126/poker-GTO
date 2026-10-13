use crate::tree::{Action, Config, Node, Tree};
use holdem::{HandClass, NUM_CLASSES};
use std::io::{self, Read, Write};

const N: usize = NUM_CLASSES;
const MAGIC: &[u8; 8] = b"PFSTRAT1";

/// 求解结果的附加信息。
#[derive(Clone, Debug)]
pub struct Meta {
    pub iterations: u32,
    /// 所有位置里最大的可提升幅度，bb/100 手。
    pub max_gain_per_100: f32,
}

/// 保存策略。每个概率量化成一个字节（精度约 0.4%），树可以由配置重新生成，所以不存树。
pub fn save(mut w: impl Write, tree: &Tree, strategy: &[f64], meta: &Meta) -> io::Result<()> {
    let c = &tree.config;
    w.write_all(MAGIC)?;
    w.write_all(&[c.players as u8])?;
    for v in [
        c.stack,
        c.small_blind,
        c.big_blind,
        c.open,
        c.three_bet_ip,
        c.three_bet_oop,
        c.four_bet_ip,
        c.four_bet_oop,
    ] {
        w.write_all(&v.to_le_bytes())?;
    }
    w.write_all(&meta.iterations.to_le_bytes())?;
    w.write_all(&meta.max_gain_per_100.to_le_bytes())?;
    w.write_all(&(strategy.len() as u64).to_le_bytes())?;
    let mut bytes = Vec::with_capacity(strategy.len());
    for node in &tree.nodes {
        if let Node::Decision {
            actions, offset, ..
        } = node
        {
            let a = actions.len();
            for h in 0..N {
                let i = offset + h * a;
                bytes.extend(quantize(&strategy[i..i + a]));
            }
        }
    }
    w.write_all(&bytes)
}

/// 读回配置、策略和附加信息。
pub fn load(mut r: impl Read) -> io::Result<(Config, Vec<f64>, Meta)> {
    let bad = |msg: &str| io::Error::new(io::ErrorKind::InvalidData, msg.to_string());
    let mut magic = [0u8; 8];
    r.read_exact(&mut magic)?;
    if &magic != MAGIC {
        return Err(bad("不是翻前策略文件"));
    }
    let mut players = [0u8; 1];
    r.read_exact(&mut players)?;
    let mut f32s = [0f32; 10];
    let mut buf = [0u8; 4];
    for v in &mut f32s[..8] {
        r.read_exact(&mut buf)?;
        *v = f32::from_le_bytes(buf);
    }
    let mut config = Config::new(players[0] as usize);
    [
        config.stack,
        config.small_blind,
        config.big_blind,
        config.open,
        config.three_bet_ip,
        config.three_bet_oop,
        config.four_bet_ip,
        config.four_bet_oop,
    ] = f32s[..8].try_into().unwrap();
    r.read_exact(&mut buf)?;
    let iterations = u32::from_le_bytes(buf);
    r.read_exact(&mut buf)?;
    let max_gain_per_100 = f32::from_le_bytes(buf);
    let mut len = [0u8; 8];
    r.read_exact(&mut len)?;
    let len = u64::from_le_bytes(len) as usize;
    let mut bytes = vec![0u8; len];
    r.read_exact(&mut bytes)?;
    let strategy = bytes.iter().map(|&b| b as f64 / 255.0).collect();
    Ok((
        config,
        strategy,
        Meta {
            iterations,
            max_gain_per_100,
        },
    ))
}

/// 把一行概率量化成和为 255 的字节（最大余数法）。
fn quantize(probs: &[f64]) -> Vec<u8> {
    let scaled: Vec<f64> = probs.iter().map(|p| p * 255.0).collect();
    let mut out: Vec<u8> = scaled.iter().map(|s| s.floor() as u8).collect();
    let short = 255 - out.iter().map(|&b| b as u32).sum::<u32>();
    let mut order: Vec<usize> = (0..probs.len()).collect();
    order.sort_by(|&a, &b| {
        (scaled[b] - scaled[b].floor()).total_cmp(&(scaled[a] - scaled[a].floor()))
    });
    for &i in order.iter().take(short as usize) {
        out[i] += 1;
    }
    out
}

pub fn action_label(action: Action) -> String {
    match action {
        Action::Fold => "弃牌".into(),
        Action::Call => "跟注".into(),
        Action::Raise(to) => format!("加注到 {to}"),
        Action::AllIn => "全下".into(),
    }
}

/// 常用局面（开池、面对开池、面对 3bet）的策略，导出成 JSON 给界面查看。
/// 只导出路径里最多两次主动投注（不算弃牌）、而且出现概率不低于 `min_reach` 的局面。
/// `values` 是 [`crate::action_values`] 算出的各动作 EV，和策略同样布局。
pub fn export_spots_json(
    tree: &Tree,
    strategy: &[f64],
    values: &[f64],
    meta: &Meta,
    min_reach: f64,
) -> String {
    let prior = crate::solver::prior();
    let config = &tree.config;
    let mut spots = Vec::new();
    // (节点, 路径描述, 主动投注次数, 每个座位到达该节点的范围)
    let mut stack = vec![(
        tree.root(),
        Vec::<String>::new(),
        0usize,
        vec![prior.clone(); config.players],
    )];
    while let Some((node, path, raises, ranges)) = stack.pop() {
        let Node::Decision {
            player,
            actions,
            children,
            offset,
        } = &tree.nodes[node]
        else {
            continue;
        };
        let reach: f64 = ranges.iter().map(|r| r.iter().sum::<f64>()).product();
        if reach < min_reach {
            continue;
        }
        let a = actions.len();
        let rows = &strategy[*offset..offset + N * a];
        spots.push(spot_json(
            config.position_name(*player),
            &path,
            actions,
            rows,
            &values[*offset..offset + N * a],
            &ranges[*player],
            reach,
        ));
        for (k, (&action, &child)) in actions.iter().zip(children).enumerate() {
            let next_raises = raises + usize::from(action != Action::Fold);
            if next_raises > 2 && action != Action::Fold {
                continue;
            }
            let mut next_ranges = ranges.clone();
            for h in 0..N {
                next_ranges[*player][h] *= rows[h * a + k];
            }
            let mut next_path = path.clone();
            next_path.push(format!(
                "{} {}",
                config.position_name(*player),
                action_label(action)
            ));
            stack.push((child, next_path, next_raises, next_ranges));
        }
    }
    spots.reverse();
    let positions: Vec<String> = (0..config.players)
        .map(|s| format!("\"{}\"", config.position_name(s)))
        .collect();
    format!(
        "{{\"players\":{},\"stack\":{},\"iterations\":{},\"max_gain_per_100\":{:.3},\"positions\":[{}],\"hands\":[{}],\"spots\":[\n{}\n]}}\n",
        config.players,
        config.stack,
        meta.iterations,
        meta.max_gain_per_100,
        positions.join(","),
        HandClass::all()
            .map(|h| format!("\"{}\"", h.name()))
            .collect::<Vec<_>>()
            .join(","),
        spots.join(",\n")
    )
}

fn spot_json(
    actor: &str,
    path: &[String],
    actions: &[Action],
    rows: &[f64],
    values: &[f64],
    range: &[f64],
    reach: f64,
) -> String {
    let a = actions.len();
    let labels: Vec<String> = actions
        .iter()
        .map(|&x| format!("\"{}\"", action_label(x)))
        .collect();
    let history: Vec<String> = path.iter().map(|s| format!("\"{s}\"")).collect();
    // 每手牌：到达该局面的相对权重，以及各动作频率（三位小数）。
    let total: f64 = range.iter().sum();
    let hands: Vec<String> = (0..N)
        .map(|h| {
            let freqs: Vec<String> = (0..a).map(|k| format!("{:.3}", rows[h * a + k])).collect();
            let weight = if total > 0.0 {
                range[h] / total * N as f64
            } else {
                0.0
            };
            format!("[{:.3},{}]", weight, freqs.join(","))
        })
        .collect();
    // 每手牌各动作的 EV，单位 bb，按整手牌净输赢计，两位小数。
    let evs: Vec<String> = (0..N)
        .map(|h| {
            let ev: Vec<String> = (0..a)
                .map(|k| format!("{:.2}", values[h * a + k]))
                .collect();
            format!("[{}]", ev.join(","))
        })
        .collect();
    format!(
        "{{\"actor\":\"{}\",\"history\":[{}],\"reach\":{:.5},\"actions\":[{}],\"hands\":[{}],\"ev\":[{}]}}",
        actor,
        history.join(","),
        reach,
        labels.join(","),
        hands.join(","),
        evs.join(",")
    )
}
