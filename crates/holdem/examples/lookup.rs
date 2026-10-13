//! 查询胜率表：`cargo run --release --example lookup -- AA KK`
use holdem::{EquityTable, HandClass};

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::File::open("data/equity_hu_169.bin").expect("缺少胜率表");
    let table = EquityTable::read_from(std::io::BufReader::new(file)).unwrap();
    for pair in args.chunks(2) {
        let (a, b) = (
            HandClass::from_name(&pair[0]).unwrap(),
            HandClass::from_name(&pair[1]).unwrap(),
        );
        println!("{} 对 {}：{:.4}", pair[0], pair[1], table.get(a, b));
    }
}
