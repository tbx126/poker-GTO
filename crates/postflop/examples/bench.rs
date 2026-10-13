//! 计时：从翻前范围表取一条行动线，在给定翻牌上做精确求解。
//! 用法：cargo run --release -p postflop --example bench -- [桌型] [翻牌] [线]
//! 线目前支持 srp（某位置开池、大盲跟注）和 3bp（大盲 3bet、开池者跟注），开池者默认按钮位。

use holdem::parse_card;
use postflop::{build_game, range_from_classes, solve, Sizes, SolveOptions, Spot};
use preflop::{follow_line, load, Action, Config, Tree};
use std::fs::File;
use std::sync::atomic::AtomicBool;
use std::time::Instant;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let players: usize = args.get(1).map_or(6, |s| s.parse().unwrap());
    let flop = args.get(2).map_or("Td9d6h", String::as_str);
    let line = args.get(3).map_or("srp", String::as_str);

    let path = format!("data/preflop/{players}max.bin");
    let (config, strategy, _) =
        load(File::open(&path).expect("先运行翻前求解生成范围表")).expect("读取范围表失败");
    let tree = Tree::build(config);
    let config: &Config = &tree.config;
    let opener = if players == 2 { 0 } else { players - 3 };
    let bb = players - 1;
    let mut actions = Vec::new();
    for _ in 0..opener {
        actions.push(Action::Fold);
    }
    actions.push(Action::Raise(config.open));
    for _ in opener + 1..bb {
        actions.push(Action::Fold);
    }
    if line == "3bp" {
        let three = preflop_raise(&tree, &actions);
        actions.push(three);
        actions.push(Action::Call);
    } else {
        actions.push(Action::Call);
    }
    let result = follow_line(&tree, &strategy, &actions).expect("行动线不在树里");
    let pot: f32 = result.contrib.iter().sum();
    let stack = config.stack - result.contrib[bb];
    let (oop, ip) = (bb, opener);

    let board: Vec<_> = (0..flop.len() / 2)
        .map(|i| parse_card(&flop[2 * i..2 * i + 2]).unwrap())
        .collect();
    let spot = Spot {
        board,
        ranges: [
            range_from_classes(&result.ranges[oop]),
            range_from_classes(&result.ranges[ip]),
        ],
        pot,
        stack,
    };
    println!(
        "{players} 人桌 {} vs {} {line}，底池 {pot}bb，有效筹码 {stack}bb，公共牌 {flop}",
        config.position_name(oop),
        config.position_name(ip)
    );
    let sizes = Sizes::precise(spot.board.len());
    let t0 = Instant::now();
    let mut game = build_game(&spot, &sizes, false).unwrap();
    let (mem, mem_c) = game.memory_usage();
    println!(
        "建树 {:.1} 秒，内存 {:.2}GB（压缩后 {:.2}GB）",
        t0.elapsed().as_secs_f32(),
        mem as f64 / 1e9,
        mem_c as f64 / 1e9
    );
    let cancel = AtomicBool::new(false);
    let (outcome, last) = solve(&mut game, &SolveOptions::default(), &cancel, |p| {
        if p.iteration % 20 == 0 {
            println!(
                "  {:>5} 轮 {:>7.1} 秒  可剥削度 {:.3}% 底池",
                p.iteration,
                p.elapsed.as_secs_f32(),
                p.exploitability * 100.0
            );
        }
    });
    println!(
        "{:?}：{} 轮，{:.1} 秒，可剥削度 {:.3}% 底池",
        outcome,
        last.iteration,
        last.elapsed.as_secs_f32(),
        last.exploitability * 100.0
    );
}

/// 大盲面对开池时的 3bet 尺寸（树里第一个加注动作）。
fn preflop_raise(tree: &Tree, path: &[Action]) -> Action {
    let node = tree.follow(path).unwrap();
    let preflop::Node::Decision { actions, .. } = &tree.nodes[node] else {
        panic!("不是决策节点");
    };
    *actions
        .iter()
        .find(|a| matches!(a, Action::Raise(_)))
        .unwrap()
}
