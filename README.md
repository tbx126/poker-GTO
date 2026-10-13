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
- [x] 求解器接口（`crates/solver-api`）：翻后两人底池后台求解、进度、每个动作的 EV，给 Tauri 外壳调用
- [x] Tauri 桌面外壳，GitHub Actions 打 Windows 安装包
- [x] 把翻后求解器接进界面：两人底池一发牌就后台求解，显示进度，纠错用求解器的频率和 EV

## 开发

```sh
cargo test
cargo run --release --example convergence   # 查看收敛过程
cargo run --release -p preflop --example size              # 2 到 6 人下注树规模
cargo run --release -p preflop --example converge -- 3 640 # 3 人翻前求解收敛过程
cargo run --release -p preflop --bin solve -- 6          # 求解并导出 6 人范围表（含各动作 EV）到 data/preflop/
cargo run --release -p preflop --bin export -- 6         # 不重新求解，只从已保存的 6 人范围表重新导出 JSON
cargo run --release -p postflop --example bench -- 6 Td9d6h srp  # 6 人桌 BTN 开池 BB 跟注的翻牌求解计时
cargo run --release -p solver-api --example smoke -- hand.json 5   # 按前端的手牌状态求解，打印座位 5 的策略
cargo run --release -p solver-api --example fixture        # 重新生成前端对照用的翻后动作表 app/tests/fixtures/postflop-moves.json
```

## 界面

`app/` 是 React + TypeScript 前端，`app/src-tauri/` 是 Tauri 桌面外壳。

```sh
cd app
npm install
npm run dev      # 本地预览
npm test         # 规则引擎和纠错的单元测试
npm run build    # 打包到 app/dist
npm run tauri dev    # 以桌面应用运行（需要 Rust，Windows 自带 WebView2）
npm run tauri build  # 打 Windows 安装包，输出在 src-tauri/target/release/bundle/nsis/
```

每个 PR 的 CI 都会在 Windows 上打一次安装包，在那次运行的 Artifacts 里下载 `windows-installer`。

桌面应用的翻后两人底池由 `crates/solver-api` 实时求解，需要完整的翻前策略 `app/src-tauri/resources/preflop/<人数>max.bin`。
CI 会自动生成并打进安装包；本地开发时运行 `cargo run --release -p preflop --bin solve -- <人数>`，再把 `data/preflop/<人数>max.bin` 复制过去。
缺少这些文件时，翻后会退回规则近似。

- `src/engine/`：牌型评估、蒙特卡洛胜率、2 到 6 人现金局规则引擎。翻前动作和尺寸与 `crates/preflop` 的下注树一致，测试会逐个核对范围表里的局面。
- `src/gto/`：策略来源。翻前查范围表，翻后通过 `setPostflopSolver` 接入求解器，没接入时用规则近似并在界面上标注“近似”。
- `app/public/ranges/` 是求解器导出的范围表。重新求解后，把 `data/preflop/<人数>max.json` 复制过来即可。
