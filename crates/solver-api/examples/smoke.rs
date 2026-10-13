//! 手动检查：读一个 HandState JSON，求解后打印某个座位的策略。
//! `cargo run --release -p solver-api --example smoke -- <hand.json> <座位> [范围表目录，默认 data/preflop]`

use solver_api::{Engine, EngineOptions, HandState};
use std::path::Path;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let state: HandState =
        serde_json::from_str(&std::fs::read_to_string(&args[1]).expect("读取 JSON 失败"))
            .expect("JSON 格式不对");
    let seat: usize = args[2].parse().expect("座位必须是数字");
    let dir = args.get(3).map_or("data/preflop", String::as_str);
    let engine = Engine::new(Path::new(dir), EngineOptions::default());
    println!("支持：{}", engine.supports(&state));
    engine
        .prepare(&state, |p| {
            if p.iteration % 50 == 0 || p.done {
                println!(
                    "  第 {} 条街 {:>4} 轮  可剥削度 {:.3}%  进度 {:.0}%",
                    p.street,
                    p.iteration,
                    p.exploitability * 100.0,
                    p.fraction * 100.0
                );
            }
        })
        .unwrap();
    match engine.strategy(&state, seat) {
        Ok(s) => println!("{}", serde_json::to_string_pretty(&s).unwrap()),
        Err(e) => println!("出错：{e}"),
    }
}
