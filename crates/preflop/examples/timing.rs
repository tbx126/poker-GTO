//! 测每轮迭代耗时：`cargo run --release --example timing -- <人数> <轮数>`
use preflop::{Config, Model, Solver, Tree};
use std::time::Instant;

fn main() {
    let mut args = std::env::args().skip(1);
    let players: usize = args.next().map_or(5, |s| s.parse().unwrap());
    let iterations: usize = args.next().map_or(3, |s| s.parse().unwrap());
    let tree = Tree::build(Config::new(players));
    let model = Model::load_default().expect("缺少胜率表");
    let mut solver = Solver::new(&tree, &model);
    let start = Instant::now();
    solver.run(iterations);
    let per = start.elapsed().as_secs_f64() / iterations as f64;
    println!("{players} 人：每轮 {per:.2} 秒（单线程）");
}
