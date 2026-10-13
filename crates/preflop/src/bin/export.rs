//! 不重新求解，只从已保存的范围表重新导出 JSON（含各动作 EV）：
//! `cargo run --release -p preflop --bin export -- <人数>`
use preflop::{action_values, export_spots_json, load, Model, Tree};
use std::fs::File;
use std::io::BufReader;

fn main() -> std::io::Result<()> {
    let players: usize = std::env::args()
        .nth(1)
        .map_or(6, |s| s.parse().expect("人数必须是 2 到 6"));
    let bin = format!("data/preflop/{players}max.bin");
    let (config, strategy, meta) = load(BufReader::new(File::open(&bin)?))?;
    let tree = Tree::build(config);
    let model = Model::load_default()?;
    let values = action_values(&tree, &model, &strategy);
    let json = format!("data/preflop/{players}max.json");
    std::fs::write(
        &json,
        export_spots_json(&tree, &strategy, &values, &meta, 0.001),
    )?;
    println!("已写入 {json}");
    Ok(())
}
