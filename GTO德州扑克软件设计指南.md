## ---

**document\_type: AI-Readable System Design Specification domain: Imperfect-Information Game Solver (Texas Hold'em) format\_rules: Hierarchical headings, concise bullet points, clear separation of architecture and logic**

# **GTO德州扑克软件设计指南**

## **1\. 核心需求与系统目标 (Requirements & Objectives)**

### **1.1 业务定位**

构建面向2026年市场的新一代德州扑克辅助系统，全面取代依赖本地算力的传统买断制求解器。系统需通过云原生架构提供秒级高精度求解、实战数据分析与游戏化闭环训练。

### **1.2 关键功能需求**

* **高并发实时推演:** 支持多达9人的翻前复杂动态树及翻后多尺度的即时求解。  
* **深度节点锁定 (Node-Locking):** 支持非对称博弈计算，强制干预真实玩家错误频率以生成最大化剥削策略。  
* **海量数据分析 (MDA) 引擎:** 支持三亿级别以上的真实牌局数据清洗，提炼群体行为画像。  
* **智能化训练模拟器 (GTO Trainer):** 具备手牌历史漏洞自动扫描与基于记忆曲线的间隔重复纠错训练。

## **2\. 技术栈选型与系统架构 (Tech Stack & Architecture)**

### **2.1 算法与模型基座 (AI & Algorithm Engine)**

* **核心网络架构选型:** 采用**基于语义分组Token的Transformer (Grouped-Token Transformer)**。为避免庞大状态空间导致的算力崩溃，需将141维原始特征压缩为24个具备高维语义的Token（如CARD、ROUND、STATE以及最高20步的历史动作序列ACT Token）。此举可使注意力对数骤减34.5倍，大幅提高大模型样本下的验证精度与训练效率 1。  
* **神经网络强化学习:** 部署**深度反事实遗憾最小化 (Deep CFR)**。利用经验回放缓冲区与深层神经网络，直接预测完整博弈树的行为遗憾值，彻底消除旧时代因手动抽象化（Abstraction）引起的核心战术信息丢失 2。  
* **高速计算模式:** 摒弃逐节点遍历全树的传统CFR范式，转而利用价值网络的“直觉”直接估算预期价值（EV）。计算时采用单街推演（One street at a time），在维持超高精度的同时，将复杂博弈树的响应时间惊人地压缩至单街平均3秒以内 3。  
* **多样性策略生成:** 在底层引入偏好驱动的CFR（Pref-CFR）算法，允许动态输出诸如“高波动攻击型”或“平稳防守型”的非唯一标准均衡打法。

### **2.2 底层数据结构 (Data Structures & Execution)**

* **状态高效编码:** 强烈建议在底层游戏状态表达中引入**位棋盘 (Bitboards)** 数据结构。通过64位长整数对牌面与掩码进行按位逻辑运算，能够以极小的内存占用实现非法操作过滤与合法动作树的超高速生成，从而成倍提升单次迭代的计算吞吐量。  
* **通信与序列化格式:** 前后端的高频通信应采用Protobuf等强类型、高压缩比的二进制协议，以适应毫秒级的UI响应要求。

### **2.3 云原生基础设施 (Cloud & Backend Platform)**

* **分布式任务调度:** 前端仅作为轻量化渲染视窗，通过RESTful API/WebSocket将博弈参数发送至后端高并发服务器矩阵。  
* **云服务平台优化:** 针对高强度算力需求的神经网络预计算与推理任务（Compute-intensive workloads），架构师应优先考虑部署在 **Google Cloud Platform (GCP)**。相比于AWS，GCP对于此类定制化机器和持续使用实例的折扣力度更大，总体计算成本往往可降低20%至35%。  
* **双轨数据库引擎:** 标准预计算解答（如常规翻后100bb深度）存储于Redis集群的列式结构中实现瞬时响应；复杂的自定义请求分配至专属GPU/CPU弹性实例进行实时演算。

## **3\. 前端交互逻辑与UI/UX (Interaction Logic & UI)**

### **3.1 界面可视化与认知减负**

* **单屏全局视图:** 抛弃传统软件多窗口叠加的冗杂设计，严格使用双向面板（Side-by-side）结构，在同一视距内并排呈现进攻方与防守方的范围分布、预期净值（EV）和胜率。  
* **动作色彩规范:** 强行推行行业标准的颜色映射直觉：冷色系（蓝色/紫色）映射为弃牌，中性色（绿色）映射为过牌/平跟，渐变暖色（从浅红至深暗红）精准表达从小尺度试探到全下（All-in）的激进程度。

### **3.2 节点锁定交互链路 (Node-Locking Workflow)**

* **输入交互:** 用户无需面对密集的数字矩阵，直接在手牌热力图上使用交互式“画笔”工具批量选中牌型，或拖动全局频率滑块进行平滑修改。  
* **后端波及联动:** 约束参数下发后，底层引擎即刻基于“对手在犯下该错误后，后续街道将试图以完美策略来弥补”的前提进行重算 4。UI界面必须以高亮的形式，直观呈现这种跨越多个下注轮次的连锁策略适应性改变。

### **3.3 大规模数据分析 (MDA) 实战映射逻辑**

* **自动化特征调用:** 在遭遇难解局面时，用户点击“应用群体倾向”按钮，前端将实时调用脱敏的三亿手数据库，提取目标玩家原型（如VPIP极高的娱乐玩家）在当前牌面结构的真实诈唬概率。  
* **一键剥削生成:** 系统自动将该真实世界统计数据作为硬性约束写入当前博弈树，瞬间将其转化为反制网络平均环境漏洞的最高EV剥削打法。

### **3.4 动态训练营反馈闭环 (GTO Trainer Feedback Loop)**

* **针对性训练配置:** 允许用户自定义细分场景（如仅练习按钮位对抗大盲位且面临超额下注的转牌决策）。  
* **多维度诊断反馈:** 用户的每一次行动不仅会被贴上对错标签，UI还会精确弹窗反馈该决策带来的相对“EV损失绝对值”。系统内置一键剖析功能，利用底层数据解释为何缺乏特定阻挡牌（Blockers）会导致策略降级。  
* **自动薄弱项捕获:** 平台通过解析用户上传的真实对局Hand History文件，使用算法精准定位资金流失节点，并自动将这些痛点打包成每日专属复习关卡，从而建立起无法割舍的用户留存闭环。

#### **引用的著作**

1. (PDF) Scaling Laws for Counterfactual Value Prediction in No-Limit ..., 访问时间为 五月 2, 2026， [https://www.researchgate.net/publication/399734719\_Scaling\_Laws\_for\_Counterfactual\_Value\_Prediction\_in\_No-Limit\_Hold'em\_MLPs\_vs\_Grouped-Token\_Transformers](https://www.researchgate.net/publication/399734719_Scaling_Laws_for_Counterfactual_Value_Prediction_in_No-Limit_Hold'em_MLPs_vs_Grouped-Token_Transformers)  
2. Deep Counterfactual Regret Minimization | Facebook AI Research \- Meta AI, 访问时间为 五月 2, 2026， [https://ai.meta.com/research/publications/deep-counterfactual-regret-minimization/](https://ai.meta.com/research/publications/deep-counterfactual-regret-minimization/)  
3. GTO Wizard AI Explained, 访问时间为 五月 2, 2026， [https://blog.gtowizard.com/gto-wizard-ai-explained/](https://blog.gtowizard.com/gto-wizard-ai-explained/)  
4. Node Locking in Postflopizer GTO Solver \- ICMizer, 访问时间为 五月 2, 2026， [https://www.icmizer.com/en/blog/node-locking-in-postflopizer-gto-solver/](https://www.icmizer.com/en/blog/node-locking-in-postflopizer-gto-solver/)