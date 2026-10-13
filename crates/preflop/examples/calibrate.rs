//! 调实现率参数时看关键频率：
//! `cargo run --release --example calibrate -- <人数> <轮数> <ip> <oop> <slope> <suited>`
use holdem::HandClass;
use preflop::{prior, Action, Config, Model, Node, Realization, Solver, Tree};

/// 某个节点上，按先验组合数加权的各动作频率。
fn mix(tree: &Tree, strategy: &[f64], path: &[Action]) -> Vec<(Action, f64)> {
    let node = tree.follow(path).expect("路径存在");
    let Node::Decision {
        actions, offset, ..
    } = &tree.nodes[node]
    else {
        panic!("不是决策节点")
    };
    let a = actions.len();
    let p = prior();
    actions
        .iter()
        .enumerate()
        .map(|(k, &act)| {
            let f: f64 = HandClass::all()
                .map(|h| p[h.index()] * strategy[offset + h.index() * a + k])
                .sum();
            (act, f)
        })
        .collect()
}

fn main() {
    let args: Vec<f64> = std::env::args()
        .skip(1)
        .map(|s| s.parse().unwrap())
        .collect();
    let players = args[0] as usize;
    let realization = Realization {
        ip: args[2],
        oop: args[3],
        slope: args[4],
        suited_bonus: args[5],
    };
    let tree = Tree::build(Config::new(players));
    let model = Model::load(realization).unwrap();
    let mut solver = Solver::new(&tree, &model);
    solver.run(args[1] as usize);
    let s = solver.average_strategy();
    let config = &tree.config;

    let mut line = Vec::new();
    for seat in 0..players - 1 {
        let path = vec![Action::Fold; seat];
        let open = mix(&tree, &s, &path)
            .iter()
            .filter(|(a, _)| *a != Action::Fold)
            .map(|(_, f)| f)
            .sum::<f64>();
        let mut bb_path = path.clone();
        bb_path.push(Action::Raise(config.open));
        bb_path.extend(vec![Action::Fold; players - 2 - seat]);
        let defend = mix(&tree, &s, &bb_path);
        let fold = defend[0].1;
        line.push(format!(
            "{} 开池 {:.0}% / 大盲弃牌 {:.0}%",
            config.position_name(seat),
            open * 100.0,
            fold * 100.0
        ));
    }
    println!("{realization:?}\n  {}", line.join("\n  "));
}
