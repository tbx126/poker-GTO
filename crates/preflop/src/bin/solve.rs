//! 求解并保存翻前范围表：
//! `cargo run --release -p preflop --bin solve -- <人数> [目标 bb/100，默认 0.5] [最多轮数，默认 5000]`
//!
//! 输出 `data/preflop/<人数>max.bin`（完整策略）和 `data/preflop/<人数>max.json`（常用局面，给界面查看）。
use preflop::{evaluate, export_spots_json, save, Config, Meta, Model, Solver, Tree};
use std::io::BufWriter;
use std::time::Instant;

fn main() -> std::io::Result<()> {
    let mut args = std::env::args().skip(1);
    let players: usize = args
        .next()
        .map_or(6, |s| s.parse().expect("人数必须是 2 到 6"));
    let target: f64 = args
        .next()
        .map_or(0.5, |s| s.parse().expect("目标必须是数字"));
    let max_iterations: usize = args
        .next()
        .map_or(5000, |s| s.parse().expect("轮数必须是整数"));

    let tree = Tree::build(Config::new(players));
    let model = Model::load_default()?;
    let mut solver = Solver::new(&tree, &model);
    println!(
        "{players} 人，{} 个决策节点，{} 线程，目标 {target} bb/100",
        tree.num_decisions(),
        rayon::current_num_threads()
    );

    let start = Instant::now();
    let mut gain;
    let mut check = 50;
    loop {
        solver.run(check.min(max_iterations) - solver.iterations());
        gain = evaluate(&tree, &model, &solver.average_strategy()).max_gain_per_100();
        println!(
            "{:>6} 轮  {:>7.1} 秒  最大可提升 {gain:.3} bb/100",
            solver.iterations(),
            start.elapsed().as_secs_f64()
        );
        if gain <= target || solver.iterations() >= max_iterations {
            break;
        }
        check += 50;
    }

    let strategy = solver.average_strategy();
    let meta = Meta {
        iterations: solver.iterations() as u32,
        max_gain_per_100: gain as f32,
    };
    std::fs::create_dir_all("data/preflop")?;
    let bin = format!("data/preflop/{players}max.bin");
    save(
        BufWriter::new(std::fs::File::create(&bin)?),
        &tree,
        &strategy,
        &meta,
    )?;
    let json = format!("data/preflop/{players}max.json");
    std::fs::write(&json, export_spots_json(&tree, &strategy, &meta, 0.001))?;
    println!("已写入 {bin} 和 {json}");
    Ok(())
}
