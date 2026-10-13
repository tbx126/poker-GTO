# Poker

一个给自己用的德州扑克 GTO 训练桌面应用：和 GTO 对手打 2 到 6 人现金局，边打边看自己每一步损失了多少 EV，打完再复盘。

需求和设计决定见 [docs/alignment.md](docs/alignment.md)。

## 当前进度

- [x] CFR+ 求解器核心与可剥削度计算，用库恩扑克和 Leduc 验证（`crates/cfr`）
- [x] 七张牌型评估器、169 种起手牌、两人全下胜率表（`crates/holdem`，`data/equity_hu_169.bin`）
- [x] 翻前求解器 CPU 版（2 到 6 人，`crates/preflop`）
- [ ] 翻前求解器加速与范围表导出
- [ ] 翻后两人底池求解器（基于 postflop-solver）
- [ ] 规则引擎、牌桌界面、即时纠错、复盘

## 开发

```sh
cargo test
cargo run --release --example convergence   # 查看收敛过程
cargo run --release -p preflop --example size              # 2 到 6 人下注树规模
cargo run --release -p preflop --example converge -- 3 640 # 3 人翻前求解收敛过程
```
