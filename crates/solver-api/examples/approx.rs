//! 手动检查多人底池的规则近似：读一个 HandState JSON 和合法动作，打印策略和用时。
//! `cargo run --release -p solver-api --example approx -- <hand.json> <座位> '<合法动作 JSON>' [范围表目录]`
//! 合法动作例如 `[{"kind":"check","to":0},{"kind":"bet","to":2.6}]`。

use solver_api::{Engine, EngineOptions, HandState, LegalMove};
use std::path::Path;
use std::time::Instant;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let state: HandState =
        serde_json::from_str(&std::fs::read_to_string(&args[1]).expect("读取 JSON 失败"))
            .expect("JSON 格式不对");
    let seat: usize = args[2].parse().expect("座位必须是数字");
    let legal: Vec<LegalMove> = serde_json::from_str(&args[3]).expect("合法动作 JSON 格式不对");
    let dir = args.get(4).map_or("data/preflop", String::as_str);
    let engine = Engine::new(Path::new(dir), EngineOptions::default());
    // 第一次调用包含读取范围表。
    engine.approx(&state, seat, &legal).ok();
    let start = Instant::now();
    match engine.approx(&state, seat, &legal) {
        Ok(s) => {
            println!(
                "用时 {:.0} 毫秒，胜率 {:.1}%",
                start.elapsed().as_secs_f64() * 1000.0,
                s.equity * 100.0
            );
            for a in s.actions {
                println!(
                    "  {:?} {:>6.2}  频率 {:>5.1}%  EV {:>6.2}",
                    a.kind,
                    a.to,
                    a.freq * 100.0,
                    a.ev
                );
            }
        }
        Err(e) => println!("出错：{e}"),
    }
}
