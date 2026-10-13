//! 生成两人全下胜率表：`cargo run --release --bin gen-equity -- [每对抽样数] [输出路径]`
use holdem::EquityTable;
use std::time::Instant;

fn main() -> std::io::Result<()> {
    let mut args = std::env::args().skip(1);
    let samples: usize = args
        .next()
        .map_or(200_000, |s| s.parse().expect("抽样数必须是整数"));
    let path = args
        .next()
        .unwrap_or_else(|| "data/equity_hu_169.bin".into());
    let threads = std::thread::available_parallelism().map_or(1, |n| n.get());

    let start = Instant::now();
    let table = EquityTable::compute(samples, threads, 0x5EED);
    let file = std::fs::File::create(&path)?;
    table.write_to(std::io::BufWriter::new(file))?;
    println!(
        "每对抽样 {samples} 次，{threads} 线程，用时 {:.1} 秒，写入 {path}",
        start.elapsed().as_secs_f64()
    );
    Ok(())
}
