# Poker GTO

云原生德州扑克 GTO 求解系统的渐进式实现，遵循 `GTO德州扑克软件设计指南.md`。

## 目录

```
engine/       位棋盘状态、手牌评估、合法动作树
solver/       CFR+ 表格求解器（Kuhn / Leduc）+ Deep CFR 神经网络求解器
solver/deep_cfr/  Deep CFR 模块：价值网络、策略网络、Grouped-Token 编码器
solver/games/ 游戏实现：Kuhn、Leduc、翻后德州扑克
api/          FastAPI 服务层
web/          React + Vite 前端：13×13 范围热力图 + 双向面板
tests/        pytest 单元与收敛测试
```

## 进度

- [x] **M1** 位棋盘 + 7 张牌评估器；表格 CFR+ 在 Kuhn / Leduc 上收敛；前端壳与 13×13 热力图
- [x] **M2** FastAPI 服务 + 跨源；前端实时求解控制台带收敛曲线
- [x] **M2.5** 169 手牌类抽象 + MC equity 表 + HU 翻前向量化 CFR+；前端切到真实求解结果
- [x] **M2.6** 节点锁定：求解器按 (history, hand) 冻结策略；前端格子点选 + 锁动作；带锁求解
- [x] **M2.7** 参数化下注树：自定义筹码深度 / SB-BB / 开池 / 3bet / 4bet；动作色彩按尺度自适应
- [x] **M3** Deep CFR + Grouped-Token Transformer（神经价值网络替换表格）
- [ ] **M4** MDA 引擎 / Trainer 闭环

### M2.5 已知简化

- 翻前下注树仅含 fold / open25 / shove / 3bet9 / 4bet 几个固定档位。
- "showdown" 用 all-in equity 近似，跳过翻牌后行动——因此弱牌防守频率会偏松（真实 GTO 中需结合翻后可玩性）。
- chance 先验 P(SB=A AND BB=B) ≈ P(A)·P(B)，没有补偿手牌冲突的相关性（同对类偏差最大但绝对量极小）。
- equity 表 500 MC 样本，单元偏差 ~±2%。重建：`python -m engine.equity 1000`。

### M3 新增功能

- **Deep CFR 模块** (`solver/deep_cfr/`)
  - `ValueNetwork` / `StrategyNetwork` / `AdvantageNetwork`：神经网络替代表格存储
  - `MLPBackbone` 和 `TransformerBackbone`：两种网络架构
  - `GroupedTokenEncoder`：将游戏状态编码为语义 Token 序列
  - `RegretMatching`：将优势值转换为策略分布
  - `DeepCFRSolver`：完整的 Deep CFR 训练循环

- **翻后游戏支持** (`solver/games/holdem.py`)
  - `PostflopGame`：支持 flop/turn/river 多街游戏
  - `BettingConfig`：可配置的下注尺寸
  - 完整的摊牌评估

- **API 端点**
  - `POST /solve/postflop`：使用 Deep CFR 求解翻后场景
  - 支持自定义牌面和下注配置

## 快速开始

```powershell
# 一次性安装
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest          # 64 项测试

# 启动后端（任选端口）
python -m uvicorn api.main:app --port 8090 --reload

# 启动前端 dev server（另开一个终端）
cd web
npm install
npm run dev
# 浏览器打开 Vite 提示的 URL（默认 5173，被占则 5174）
```

如果后端不在 8090，前端会通过 `VITE_API_BASE` 覆盖：

```powershell
$env:VITE_API_BASE = "http://localhost:8080"; npm run dev
```

## CLI 验收

```powershell
# 表格 CFR+ 求解器
python -m solver.cli kuhn --iters 20000
python -m solver.cli leduc --iters 1000

# Deep CFR 求解器（需要 PyTorch）
python -c "from solver.deep_cfr import DeepCFRSolver; from solver.games.kuhn import KuhnGame; s = DeepCFRSolver(KuhnGame()); s.train(10)"
```

## 设计来源

详见同目录 `GTO德州扑克软件设计指南.md`。架构对齐其中的：

- 位棋盘 + Protobuf 通信（`engine/`）
- Deep CFR + Grouped-Token Transformer（`solver/deep_cfr/`）
- 双向面板 / 颜色规范（`web/`）
- 节点锁定 / MDA / Trainer（M4）
