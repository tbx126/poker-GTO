# Poker

一个给自己用的德州扑克 GTO 训练桌面应用：和 GTO 对手打 2 到 6 人现金局，边打边看自己每一步损失了多少 EV，打完再复盘。

需求和设计决定见 [docs/alignment.md](docs/alignment.md)。

## 当前进度

- [x] CFR+ 求解器核心与可剥削度计算，用库恩扑克和 Leduc 验证（`crates/cfr`）
- [x] 七张牌型评估器、169 种起手牌、两人全下胜率表（`crates/holdem`，`data/equity_hu_169.bin`）
- [x] 翻前求解器 CPU 版（2 到 6 人，`crates/preflop`）
- [x] 翻前求解器加速与范围表导出
- [x] 翻后两人底池求解器（`crates/postflop`，源码复制自 postflop-solver，见 `crates/postflop-solver`）
- [x] 界面：规则引擎、牌桌、即时纠错、复盘、翻前范围查看与导入（`app/`，翻后暂用规则近似）
- [ ] Tauri 外壳，把翻后求解器接进界面

## 开发

```sh
cargo test
cargo run --release --example convergence   # 查看收敛过程
cargo run --release -p preflop --example size              # 2 到 6 人下注树规模
cargo run --release -p preflop --example converge -- 3 640 # 3 人翻前求解收敛过程
cargo run --release -p preflop --bin solve -- 6          # 求解并导出 6 人范围表（含各动作 EV）到 data/preflop/
cargo run --release -p preflop --bin export -- 6         # 不重新求解，只从已保存的 6 人范围表重新导出 JSON
cargo run --release -p postflop --example bench -- 6 Td9d6h srp  # 6 人桌 BTN 开池 BB 跟注的翻牌求解计时
```

## 界面

`app/` 是 React + TypeScript 前端，之后由 Tauri 打包成桌面应用。

```sh
cd app
npm install
npm run dev      # 本地预览
npm test         # 规则引擎和纠错的单元测试
npm run build    # 打包到 app/dist
```

- `src/engine/`：牌型评估、蒙特卡洛胜率、2 到 6 人现金局规则引擎。翻前动作和尺寸与 `crates/preflop` 的下注树一致，测试会逐个核对范围表里的局面。
- `src/gto/`：策略来源。翻前查范围表，翻后通过 `setPostflopSolver` 接入求解器，没接入时用规则近似并在界面上标注“近似”。
- `app/public/ranges/` 是求解器导出的范围表。重新求解后，把 `data/preflop/<人数>max.json` 复制过来即可。
