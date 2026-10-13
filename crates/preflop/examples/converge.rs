//! 观察收敛：`cargo run --release --example converge -- <人数> <总轮数>`
use preflop::{evaluate, Config, Model, Solver, Tree};
use std::time::Instant;

fn main() {
    let mut args = std::env::args().skip(1);
    let players: usize = args.next().map_or(2, |s| s.parse().unwrap());
    let total: usize = args.next().map_or(1000, |s| s.parse().unwrap());
    let tree = Tree::build(Config::new(players));
    let model = Model::load_default().expect("缺少胜率表");
    let mut solver = Solver::new(&tree, &model);
    let start = Instant::now();
    let mut next = 10;
    while solver.iterations() < total {
        solver.run(next.min(total) - solver.iterations());
        let report = evaluate(&tree, &model, &solver.average_strategy());
        let gains: Vec<String> = report
            .gains()
            .iter()
            .map(|g| format!("{:.2}", g * 100.0))
            .collect();
        let ev: Vec<String> = report.ev.iter().map(|g| format!("{:+.3}", g)).collect();
        println!(
            "{:>6} 轮 {:>7.1} 秒  各位置可提升 bb/100 [{}]  期望 bb [{}]",
            solver.iterations(),
            start.elapsed().as_secs_f64(),
            gains.join(", "),
            ev.join(", ")
        );
        next *= 2;
    }
}
