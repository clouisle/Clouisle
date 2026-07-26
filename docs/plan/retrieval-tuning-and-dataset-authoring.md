# 检索参数自动调优与评估数据集构建 设计文档

> 关联：`docs/plan/yun-117-knowledge-retrieval-lab.md`（YUN-117 已完成的统一检索与批量评估基础设施）、`docs/dev/design/ai-data/KNOWLEDGE_BASE_SPEC.md`

## 背景与目标

### 现状

YUN-117 已经交付了可用的底座：统一检索服务（Dense + BM25 加权 RRF + 全局 rerank）、持久化评估数据集/用例/运行、确定性指标（Recall/MRR/nDCG/expected-empty 准确率/延迟分位）、Celery 异步执行、不可变运行配置快照。

但"批量评估"这一层目前只是**手工试错的记分板**，不是调优工具。具体问题（均已在代码中核实）：

**问题组 A — 没有参数搜索，只有预设**

1. 一次 `EvaluationRun` 只评估一个配置（`EvaluationRun.config_snapshot` 是单个配置），且只能"用当前 A 侧配置开始运行"（`retrieval-lab.tsx` 的 `startRun`）。要比较 5 个配置就要人工改参数、点 5 次、自己记住 5 组数字。
2. 所谓"预设"（`Preset`）只是 **localStorage 里的命名配置**，用于人工 A/B 对照，不参与任何自动搜索。它是"手工笔记"，不是"调优"。
3. **没有任何跨运行对比视图**：没有基线、没有 Δ、没有逐用例胜负统计。`summary_metrics` 只有均值，两次运行差 0.01 是改进还是噪声无从判断。
4. **致命断点：调优出来的参数无法落到生产。** `KnowledgeBaseSettings`（`backend/app/schemas/knowledge_base.py:53`）只有 `chunk_size / chunk_overlap / separator / rerank_enabled / rerank_candidate_k / rerank_score_threshold`，**没有** `search_mode / top_k / score_threshold / dense_weight / lexical_weight / rrf_k`。因此 `applyPreset` 只能写回 3 个 rerank 字段，其余参数被静默丢弃——"应用到生产"目前是半真的。调优若不解决这一点，等于算完就扔。

**问题组 B — 数据集根本没法建**

5. 建用例要在 Textarea 里**手写 chunk UUID 到分数的 JSON**（`chunkRelevance = 'Chunk relevance JSON (IDs mapped to grades 0–3)'`）。而检索结果卡片**不显示 chunk_id**，界面上拿不到 ID；模板里给的是假 ID（`chunk-id-1`）。实际唯一可行路径是绕过 UI 去查库拿 UUID——等于不可用。
6. 交互检索里已有的人工标注（`grades`，relevant/partial/irrelevant）**是 `Record<chunkId, Grade>`，没有按查询区分**，只存 localStorage，**永远不会流入数据集**。既浪费标注工作量，又会跨查询串味（同一 chunk 在查询甲下相关、查询乙下不相关，只能存一个值）。
7. 保存用例走 `replace_cases`（`retrieval_evaluation_store.py:102`）：**先全删再重建**。改一个错别字会重建全部用例，`EvaluationCase.id` 全部变化；历史 `EvaluationCaseResult.case_id` 因 `SET_NULL` 变为 null，**逐用例的历史趋势对比在任何一次编辑后即永久失效**。
8. **指标被无标注用例污染（正确性缺陷）**：`ranking_metrics` 在 `relevant_ids` 为空时返回 `recall=0.0, mrr=0.0, ndcg=0.0`，而 `execute_evaluation_run` 的 `summary` 对**全部**用例求均值。于是：
   - `expected_empty=True` 的用例（校验强制其不能有标注）恒定贡献 0/0/0；
   - 只标了 document 没标 chunk 的用例，把 chunk 均值拉低；
   - **加入"应该返回空"的负例，会让一个更好的系统看起来更差。**
9. 没有数据集质量视图：多少用例有标注、每用例标了几个 chunk、有没有零正例用例、标注来自人还是导入——全都不知道。

### 目标

- **自动调优 = 数据集驱动的参数搜索**：给定数据集 + 目标指标 + 预算，系统自己搜索参数空间，产出带证据的推荐配置，并能一键落到生产。
- **数据集构建 = 从检索结果标注**，人不碰 UUID。
- **数量级把控**：默认预算下一次调优 ≈ 17 个配置，分钟级完成，而非小时级。
- **诚实**：不做统计上站不住的推荐；"当前配置已是最优、不建议改动"是合法且有价值的结论。

### 成功标准

| 维度 | 标准 |
|---|---|
| 简洁 | 新建一个 20 用例数据集的人工操作 ≤ 20 分钟，全程不手写任何 UUID |
| 快速 | 20 用例 × 17 配置的调优，replay 模式下 ≤ 3 分钟（含 rerank）；live 模式下 ≤ 15 分钟 |
| 准确 | 推荐配置经**生产路径复跑验证**，目标指标与搜索期估算偏差 ≤ 0.02，否则标记 drift 且不推荐 |
| 功能 | 参数空间可编辑、可取消、有成本预估、结果可对比、推荐可一键应用到生产（含确认与权限） |
| 平衡 | 目标函数带延迟护栏与错误率护栏；超预算或有失败用例的配置不进入推荐 |

### 非目标

- 不做 chunking 策略/embedding 模型的自动搜索（另一个量级的问题，改索引不是改参数）。
- 不做 learned sparse / HyDE / 多查询改写的上线（YUN-117 已明确留在评估门之外）。
- 不做在线自动调参（生产流量自适应）。本方案是**离线、人工触发、人工确认**的调优。
- 不做 LLM-as-judge 替代人工标注做金标准；LLM 只做"预标注建议"，且默认关闭（阶段 10）。

---

## 高层设计

### 概念模型

```
KnowledgeBase
  └── EvaluationDataset（数据集）
        ├── EvaluationCase（用例：query + chunk/document 相关性标注 + expected_empty）
        ├── EvaluationRun（一次运行 = 一个配置 × 全部用例）      ← 已存在
        └── EvaluationSweep（一次调优 = 一个参数空间 → N 个 Run） ← 新增
              ├── baseline run（当前生产/A 配置）
              ├── candidate runs（搜索产生，label 标明来自哪个阶段哪个轴）
              └── verification run（推荐配置走真实生产路径复跑）
```

**关键复用决策**：Sweep **不引入任何新的指标代码和结果表**，它只是"编排 N 个 EvaluationRun 并做配对比较"。指标、快照、取消、错误处理全部沿用现有 Run 机制。这是让功能范围可控的核心取舍。

### 调优搜索策略：分阶段坐标搜索

不做网格搜索（组合爆炸：5×3×3×3×3 = 405 个配置）。按检索管线的自然依赖顺序，**逐阶段只搜一个轴，其余固定在当前最优**：

| 阶段 | 轴 | 默认候选 | 配置数 |
|---|---|---|---|
| S0 | 基线 | 当前生产配置（或用户指定 A 配置） | 1 |
| S1 | `(dense_weight, lexical_weight)` | (1,0.3) (1,0.6) (1,1) (0.6,1) (0.3,1) | 5 |
| S2 | `rrf_k` | 20, 60, 120 | 3 |
| S3 | rerank 开关与候选池 | off, on@candidate_k=20, on@candidate_k=50 | 3 |
| S4 | `rerank_score_threshold` | null, 0.1, 0.3（仅当 S3 选中 on） | 3 |
| S5 | `score_threshold` | 0, 0.2, 0.35 | 3 |
| — | 验证 | 推荐配置走生产路径 | 1 |

合计 **≤ 19 个 Run**（和 = 17，非积 = 405）。参数空间可在前端编辑；每轴候选集去重后为空则跳过该阶段。

**为什么这个顺序**：权重与 `rrf_k` 决定融合排序；rerank 在融合结果之上重排；两个 threshold 是**截断**，只有在排序确定后调才有意义。反过来调（先调阈值）会得到被后续阶段推翻的局部解。

**`top_k` 不作为质量搜索轴**（重要修正）。当前 `execute_evaluation_run` 用 `k = config["top_k"]` 计算指标，于是不同 `top_k` 的配置是在**不同 k 上**比 nDCG，苹果比橘子。改为：

- Sweep 级固定 `metric_k`（默认 10），**所有配置在同一 k 上评分**；
- 每个候选配置的 `top_k` 自动钳制为 `≥ metric_k`；
- `top_k` 作为**服务参数**由用户单独设定（它是"返回多少条给下游"的成本/篇幅选择，不是质量选择）。

### 目标函数与护栏

```
objective ∈ { chunk_ndcg | chunk_recall | chunk_mrr | document_ndcg | document_recall }   默认 chunk_ndcg，均 @metric_k
```

一个配置进入推荐必须**同时**满足：

1. `objective(candidate) − objective(baseline) ≥ min_improvement`（默认 0.01 绝对值）
2. `improved_cases > regressed_cases`（逐用例配对比较，按 `case_id` 配对）
3. `error_count == 0`（有失败用例的配置在存活用例上会虚高）
4. `latency_p95 ≤ latency_p95_budget_ms`（默认：KB 有 rerank 模型时 1500，否则 300，对齐 YUN-117 的 P95 目标）
5. `expected_empty_accuracy ≥ baseline`（防止把"该返回空"的行为调坏）

不满足 → **推荐 = 基线**，结论写明"当前配置已足够好，不建议改动"。不使用 p 值等复杂统计：胜负计数 + 绝对增量门槛，无聊但稳健、可解释。

### 快速执行：replay 模式

朴素做法（每个配置走一次完整 `retrieve()`）= 20 用例 × 17 配置 = 340 次检索，带 rerank 约 8 分钟起。

**replay 模式**利用一个数学事实：融合与截断是**通道召回结果的纯函数**。

```
每个 query 只做一次「深召回探测」：
  dense  通道 @ depth = D_max, score_threshold = 0
  lexical通道 @ depth = D_max
  （D_max = 空间内所有配置的最大有效通道深度 = max(top_k, candidate_k)）

复算某个配置：
  取两个通道缓存的前 D 项（前缀截断不改变名次 → RRF 输入精确）
  → 本地施加 dense score_threshold
  → 复用生产的纯函数 _weighted_rrf(dense, lexical, dense_weight, lexical_weight, k=rrf_k)
  → 若 rerank：取融合前 candidate_k，从 (query, chunk_id) → rerank_score 缓存取分
     （每个 query 只对「所有配置候选的并集」调一次 rerank 模型）
  → 排序、施加 rerank_score_threshold、截断到 metric_k → 计分
```

代价从 340 次检索降到 **20 次深召回 + 20 次 rerank 批调用**。

**replay 的正确性边界（必须显式处理）**：

| 情形 | 处理 |
|---|---|
| rerank 适配器是 LLM listwise（`LLMRerankAdapter`），单对分数非确定 | 自动降级为 `live` 模式，前端提示原因 |
| `_weighted_rrf` 会就地修改传入 dict（`current.update(result)`、写 `score`/`fusion_rank`） | 每个配置复算前对缓存做深拷贝，否则缓存污染 |
| 混合检索 rollout 开关/kill switch 会改变真实路径 | 探测阶段读取一次开关状态并写入 `version_snapshot`；开关在调优期间变化则整个 sweep 标记 `stale` |
| AUTO 查询上下文化改写 | 不在调优范围（调优针对固定 query 文本）；文档说明 |

**验证闭环**：搜索结束后，推荐配置**必须**作为一个普通 `EvaluationRun` 走真实 `retrieve()` 复跑一次。若 `|objective_live − objective_replay| > verification_tolerance`（默认 0.02），标记 `drift`、撤回推荐、两个数字都展示。这是"快"和"准"同时成立的唯一诚实办法。

`mode: "live"` 保留为用户可选（也是降级目标）：每个配置都走生产路径，慢但零建模假设。

### 数据集构建：从检索结果标注（pooling）

核心：**候选来自检索结果，人只做"相关/部分/不相关"三选一**。

**路径 A（主路径）—— 交互检索即标注**
检索一次 → 结果卡片上已有的三个标注按钮直接写入**按查询隔离**的草稿 → 「把当前查询与标注加入数据集」→ 增量创建/更新一个用例。A/B 对比开启时，两侧结果的**并集**都可标注（这就是标准的 TREC pooling，此处免费获得）。

标注值映射：`relevant → 3`、`partial → 2`、`irrelevant → 0`。显式的 0 表示"已判定为不相关"，对指标无害（`relevant_ids` 只取 `grade > 0`），但对**池覆盖率统计**有用。高级编辑器仍可直接填 0–3。

**路径 B（提速）—— 候选池自动生成**
「为该查询生成候选池」：用**多个差异化配置**（vector-only / fulltext-only / hybrid / hybrid+rerank）各取 top-K，去重合并成候选列表，一次性批量标注（支持"全部标为不相关"再翻转少数相关项——这是人工最快路径）。

**必须用与被调优配置不同的配置来建池**，否则池偏向被调优的那一个，调优结论无效（pooling bias）。这一约束写进 UI 提示与文档。

**路径 C（可选，阶段 10）—— LLM 预标注建议**
默认关闭。LLM 给出建议分数，标注需人工确认才生效；`label_source ∈ {human, llm_confirmed, imported}` 记录来源，未确认的 LLM 标注不参与金标准。

**路径 D —— 导入/导出**
保留现有 JSON/CSV 导入（≤2MB、≤1000 用例、`validate_case_labels` 校验 ID 归属）。新增**导出**，并把"下载模板"改为"导出当前数据集"——模板里带真实 chunk ID，彻底消灭假占位 ID 的陷阱。（顺带修掉 `downloadTemplate('csv')` 存在但 UI 无入口的死代码。）

**已知固有局限（写进文档，不假装解决）**：池化标注下的 Recall 是"池内召回"，不是真实召回。因此在数据集上记录 `pool_depth`，并在指标展示处标注"基于深度 K 的池化召回"。跨数据集比较绝对值无意义，同数据集内比较配置有效。

---

## 实施计划

### 阶段 1：设计文档与索引

- **修改文件**：`docs/plan/retrieval-tuning-and-dataset-authoring.md`（本文档）、`docs/IMPLEMENTATION_PLAN.md`
- **验证**：文档链接可达，索引条目与阶段一致。

### 阶段 2：指标正确性 —— 排除无标注用例污染均值

- **修改文件**：`backend/app/services/retrieval_evaluation.py`、`backend/app/tasks/retrieval_evaluation.py`、`backend/tests/services/test_retrieval_evaluation.py`
- **具体逻辑**：
  - `CaseEvaluation` 增加 `chunk_graded: bool` / `document_graded: bool`（即对应 relevance 是否存在正例）。
  - `execute_evaluation_run` 的 `summary`：chunk 均值只对 `chunk_graded` 用例求，document 均值只对 `document_graded` 用例求；两族均无有效用例时该族指标为 `null`（不是 0）。
  - `summary_metrics` 新增 `graded_chunk_case_count` / `graded_document_case_count` / `expected_empty_count`。
  - 历史运行的 `summary_metrics` 是不可变快照，**不回填**；前端对缺失新字段做兼容渲染。
- **验证**：新增测试——(a) 纯 `expected_empty` 数据集的 chunk/document 指标为 `null` 而非 0；(b) 混合数据集中加入 expected-empty 用例后，chunk nDCG **不变**（回归当前缺陷）；(c) 只标 document 的用例不拉低 chunk 均值。

### 阶段 3：KB 检索默认参数落地（让调优结果有去处）

- **修改文件**：`backend/app/schemas/knowledge_base.py`、`backend/app/services/retrieval.py`、`backend/app/core/init_data.py`、`backend/app/api/v1/endpoints/knowledge_bases.py`、`frontend/lib/api/knowledge-bases.ts`
- **具体逻辑**：
  - `KnowledgeBaseSettings` 增加带校验的可选字段：`search_mode: Literal["vector","fulltext","hybrid"] | None`、`top_k: int | None (1..100)`、`score_threshold: float | None (0..1)`、`dense_weight: float | None (≥0)`、`lexical_weight: float | None (≥0)`、`rrf_k: int | None (1..1000)`。全部 `None` = 沿用调用方/系统默认，**行为向后兼容**。
  - 构造 `RetrievalTarget` 的位置（`chat_rag` / `chat_tools` / `workflow/executors/knowledge.py` / AgentService）在调用方未显式指定时，用 KB settings 填充 target 级覆盖。现有 `target.search_mode or request.search_mode`、`target.top_k or request.top_k` 优先级链天然支持，改动面小。
  - `settings` 为 `dict` 存储，无需 DDL；若为清晰起见不加列，则本阶段无迁移。
  - 前端 `KnowledgeBaseSettings` 接口同步；顺带移除已随「retrieval-failure-handling 阶段 10」下线的 `rerank_fail_open`（前端接口仍留有该字段）。
- **验证**：(a) 未设置 KB 默认值时，所有现有检索路径行为逐字节不变（回归现有 `test_retrieval.py`）；(b) 设置 KB 默认 `search_mode=fulltext` 后，AUTO/workflow 检索确实走 fulltext；(c) 调用方显式传参时**覆盖** KB 默认（优先级测试）。

### 阶段 4：用例增量 CRUD、导出、真实模板

- **修改文件**：`backend/app/api/v1/endpoints/retrieval_evaluations.py`、`backend/app/services/retrieval_evaluation_store.py`、`backend/app/schemas/retrieval_evaluation.py`、`frontend/lib/api/knowledge-bases.ts`
- **具体逻辑**：
  - 新增 `POST /{kb_id}/evaluation-datasets/{dataset_id}/cases`（单个新增）、`PUT .../cases/{case_id}`、`DELETE .../cases/{case_id}`，全部走 `validate_case_labels`，**保留 `case_id`**。
  - `replace_cases` 保留但仅用于导入（语义明确为"整体替换"），并在 API 文档与 UI 文案中标明会重置用例 ID。
  - 新增 `GET .../export?format=json|csv`，输出与导入完全同构（可直接回灌）。
  - 沿用 `_ensure_no_active_runs` 守卫；扩展为同时检查活跃 sweep。
- **验证**：(a) 修改一个用例后，历史 `EvaluationCaseResult.case_id` 仍指向原用例（回归当前缺陷）；(b) 导出→导入往返后用例集合等价；(c) 活跃运行/调优期间增删改用例被 400 拒绝。

### 阶段 5：Retrieval Lab 组件拆分（无行为变更）

- **修改文件**：`frontend/components/knowledge-bases/retrieval-lab.tsx`（1014 行）拆为 `retrieval-lab/index.tsx`、`retrieval-lab/shared.ts`（`Config`/`DEFAULT_CONFIG`/`runConfig`/`formatScore`/`Highlight`/`AuthenticatedMarkdownImage`）、`retrieval-lab/batch-evaluation.tsx`
- **具体逻辑**：纯搬迁 + 导出，不改任何行为。后续三个阶段各自新增文件，避免单文件继续膨胀到 2000+ 行。
- **验证**：现有 `retrieval-lab.test.tsx`（427 行）**零修改**全部通过；`bun run lint`、`bun run build` 通过。顺带修两个已发现缺陷：
  - 首条结果自动展开失效——`runSearch` 存入的是裸 `chunk_id`，渲染侧判断 `${side}:${chunk_id}`，键不匹配；
  - `downloadTemplate('csv')` 无 UI 入口（阶段 4 已用"导出"替代，此处删除死分支）。

### 阶段 6：标注工作台（前端）

- **修改文件**：`frontend/components/knowledge-bases/retrieval-lab/labeling.tsx`（新增）、`retrieval-lab/index.tsx`、`frontend/i18n/{en,zh}/knowledgeBases.json`
- **具体逻辑**：
  - `grades` 重构为 `Record<queryKey, Record<chunkId, Grade>>`（`queryKey` = 去空白归一化后的查询文本）。旧的扁平结构在读取时丢弃（已有 corrupt-JSON → `removeItem` 兜底路径可复用）。
  - 结果卡片显示可复制的 `chunk_id`（现在完全不显示）。
  - 新增「加入数据集」：把当前 query + 该 query 下的标注，经阶段 4 的增量接口写为一个用例；同 query 已存在则更新。
  - 新增「生成候选池」：并发跑 vector / fulltext / hybrid / hybrid+rerank 四个配置，去重合并，渲染为紧凑标注列表（键盘可达：`1/2/3` 三键标注 + 上下移动）；批量「全部标为不相关」。
  - 池深度写入数据集 `pool_depth`。
- **验证**：(a) 查询甲标注不影响查询乙（跨查询隔离测试）；(b) 「加入数据集」后 `getEvaluationDataset` 返回的用例标注与 UI 一致；(c) 全程无需手输 UUID 完成一个 3 用例数据集（手工走查）；(d) localStorage 旧格式不导致崩溃。

### 阶段 7：数据集质量面板

- **修改文件**：`frontend/components/knowledge-bases/retrieval-lab/batch-evaluation.tsx`、`backend/app/api/v1/endpoints/retrieval_evaluations.py`
- **具体逻辑**：数据集卡片展示——用例总数 / 有 chunk 标注的用例数 / 有 document 标注的用例数 / expected-empty 用例数 / 平均每用例正例数 / 零正例用例列表（可跳转修补）/ `pool_depth`。零正例用例给出明确警告（它们不再污染均值，但也不提供任何信号）。
- **验证**：构造含零正例与 expected-empty 的数据集，面板计数与 `summary_metrics` 的 `graded_*_count` 一致。

### 阶段 8：调优后端 —— 模型、接口、搜索策略、护栏

- **修改文件**：`backend/app/models/retrieval_evaluation.py`、`backend/app/models/__init__.py`、`backend/app/schemas/retrieval_evaluation.py`、`backend/app/services/retrieval_tuning.py`（新增）、`backend/app/api/v1/endpoints/retrieval_evaluations.py`、`backend/app/core/init_data.py`、`backend/app/main.py`、`backend/app/locales/{en,zh}/LC_MESSAGES/messages.po`
- **具体逻辑**：
  - 新模型 `EvaluationSweep`：`dataset FK / created_by FK(SET_NULL) / status(pending|running|completed|failed|canceled) / mode(replay|live) / metric_k / objective / serving_top_k / space(JSON) / guards(JSON) / baseline_config(JSON) / best_run FK(nullable) / recommendation(JSON) / version_snapshot(JSON) / task_id / error_message / created_at / started_at / finished_at`。
  - `EvaluationRun` 增列：`sweep_id UUID NULL REFERENCES evaluation_sweeps(id) ON DELETE SET NULL`、`label VARCHAR(100) NULL`、`replayed BOOLEAN DEFAULT FALSE`、`metric_k INT NULL`（null = 沿用 `config_snapshot.top_k`，保持历史运行可解释）。
  - 迁移沿用项目约定（`docs/dev/backend/migrations-and-init-data.md`）：在 `init_data.py` 新增 `init_retrieval_tuning_tables()`，与既有 `init_retrieval_evaluation_tables()` 同风格（`CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`），在 `main.py` lifespan 中于 `generate_schemas()` 前调用。
  - `retrieval_tuning.py` 纯函数部分：`expand_space(space, baseline) -> list[(label, config)]`（分阶段坐标搜索的候选枚举）、`score(run_summary, objective, metric_k)`、`compare(baseline_results, candidate_results) -> (improved, regressed, mean_delta)`、`select_recommendation(candidates, guards) -> Recommendation`。**全部无 IO，便于单测。**
  - 接口：`POST/GET .../sweeps`、`GET .../sweeps/{id}`、`POST .../sweeps/{id}/cancel`（级联 revoke 子运行）、`POST .../sweeps/{id}/apply`（把推荐配置写入 KB settings，要求 `update` 权限，非 `evaluate`）。
  - 护栏：单数据集同时只允许 1 个活跃 sweep；`configs ≤ 32`；`cases × configs ≤ 5000`；创建前返回成本预估（用例数 × 配置数 × 估计延迟 + 是否触发 rerank 计费）。
  - 权限：sweep 的增删查改沿用现有 `require_kb_evaluate`（`kb:evaluate` / `admin:knowledge-base:evaluate`）；`apply` 走 `require_kb_update`。
  - 所有面向用户的报错用 `BusinessError` + `msg_key`，en/zh 两份 `.po` 同步。
- **验证**：(a) `expand_space` 默认空间产出 17 个配置且各配置 `top_k ≥ metric_k`（纯函数单测）；(b) 不满足改进门槛时 `select_recommendation` 返回基线；(c) 超预算配置被排除但仍出现在结果列表；(d) 活跃 sweep 期间数据集变更被拒绝；(e) `apply` 缺少 `update` 权限返回 403。

### 阶段 9：调优执行器 —— replay + live + 验证

- **修改文件**：`backend/app/services/retrieval_replay.py`（新增）、`backend/app/tasks/retrieval_tuning.py`（新增）、`backend/app/tasks/retrieval_evaluation.py`
- **具体逻辑**：
  - `retrieval_replay.py`：`probe(query, target, depth) -> ChannelCache`（dense/lexical 各一次深召回，`score_threshold=0`）；`replay(cache, config, rerank_scores) -> results`（深拷贝 → 前缀截断 → 本地阈值 → 复用生产 `_weighted_rrf` → rerank 缓存取分 → 截断）；`rerank_cache` 按 `(query, chunk_id)` 缓存，每 query 对候选并集只调一次模型。
  - `retrieval_tuning.py` Celery 任务：串行推进 S1..S5，每阶段内并发评估候选（`asyncio.Semaphore`，上限 4，避免打爆 provider 限流）；每个候选写为一条 `EvaluationRun`（复用现有落库与指标计算，`replayed=True`）；每阶段结束更新 sweep 进度；每个用例前检查取消状态（沿用 `execute_evaluation_run` 的 `refresh_from_db` 模式）。
  - 降级判定：KB rerank 模型为 LLM listwise、或空间含 rerank 轴且无法保证单对确定性 → 整个 sweep 转 `live`，`version_snapshot` 记录降级原因。
  - 验证运行：推荐配置以 `replayed=False` 走真实 `retrieve()`，比对目标指标；超容差写 `recommendation.drift=True` 并撤回推荐。
  - 幂等/重投递安全：沿用现有 `update_or_create` 与状态机，Celery 重投不产生重复子运行。
- **验证**：(a) 同一配置 replay 与 live 的结果集合在无 LLM-rerank 时完全一致（关键正确性测试，用假通道数据 + 假 rerank）；(b) 深拷贝缺失会导致缓存污染——写一个断言缓存未被修改的测试；(c) 取消在阶段中途生效，子运行状态收敛；(d) rerank 模型抛错时该配置 `error_count > 0` 且被推荐排除；(e) 人为注入 0.05 偏差使验证失败 → `drift=True` 且无推荐。

### 阶段 10：调优前端

- **修改文件**：`frontend/components/knowledge-bases/retrieval-lab/tuning.tsx`（新增）、`retrieval-lab/index.tsx`、`frontend/lib/api/knowledge-bases.ts`、`frontend/i18n/{en,zh}/knowledgeBases.json`
- **具体逻辑**：
  - 批量评估内部改为三个子页签（沿用现有 `role="tablist"` 模式）：**数据集与标注 / 运行 / 调优**。
  - 调优页：目标指标与 `metric_k` 选择、服务 `top_k`、参数空间编辑（每轴候选可增删，显示"共 N 个配置"）、护栏阈值、模式（replay/live，含降级提示）、成本与时长预估 → 开始。
  - 进度：沿用现有 2s 轮询模式，展示当前阶段/已完成配置数/已用时。
  - 结果表：每配置一行——label、目标指标、Δ vs 基线、改进/回归用例数、P95、错误数、是否超护栏（灰显并注明原因）；按目标指标排序，基线行固定置顶。
  - 推荐卡：推荐配置、证据（Δ + 胜负计数 + 验证结果）、或"不建议改动"的明确结论；「应用到生产」按钮（`canUpdate` 才启用 + `window.confirm` 二次确认 + 展示将写入的**完整**参数 diff）。
  - 「预设」定位调整为"手动对照草稿"，与调优并列而非混淆；"应用到生产"改为共享动作，预设与调优推荐都能触发，且写入全量参数（依赖阶段 3）。
- **验证**：(a) 无 `evaluate` 权限时调优页只读；(b) 无 `update` 权限时「应用到生产」禁用；(c) 取消后轮询停止且状态正确；(d) 推荐为基线时不出现应用按钮；(e) `drift` 状态下展示两个数字并阻止应用。

### 阶段 11：LLM 预标注（可选，默认关闭）

- **修改文件**：`backend/app/services/retrieval_evaluation_store.py` 或新增 `retrieval_label_suggest.py`、`backend/app/core/config.py`、前端标注工作台
- **具体逻辑**：开关默认关闭。对候选池中的每个 (query, chunk) 请求结构化 0–3 建议分，带严格超时与失败静默；建议以**未确认**状态展示，人工点击确认后才写入标注，`label_source` 记录来源。绝不自动落库为金标准。
- **验证**：开关关闭时无任何模型调用；模型超时不阻塞标注流程；未确认建议不进入数据集。

### 阶段 12：i18n、类型、文档与整体验证

- **修改文件**：`frontend/i18n/{en,zh}/knowledgeBases.json`、`frontend/i18n/types/knowledgeBases.ts`（生成）、`docs/dev/design/ai-data/KNOWLEDGE_BASE_SPEC.md`、`docs/dev/api/BACKEND_API.md`、`docs/IMPLEMENTATION_PLAN.md`
- **具体逻辑**：en/zh 同步补全全部新文案；`node scripts/gen-i18n-types.ts` 重新生成类型；`node scripts/lint-translations.ts --strict` 通过；规范文档补充"调优与数据集构建"章节，含 pooling 偏差与池内召回的说明。
- **验证**：后端 `ruff check` / `ruff format --check` / `mypy app/` / `pytest`；前端 `bun run lint` / `bun run build` / `bun test --isolate`；覆盖率不低于当前门槛（后端 97.70% 行、前端 97.81% 行）。

---

## 测试策略

### 正例路径

- 指标：多标注等级下的 chunk/document Recall/MRR/nDCG 与手算值一致（已有测试扩展 graded 计数）。
- 增量 CRUD：新增/修改/删除单用例，`case_id` 稳定，历史结果关联不断。
- 标注工作台：检索 → 标注 → 加入数据集 → 数据集内容与 UI 一致。
- 候选池：四配置并集去重，数量与预期一致，池深度记录正确。
- 调优：默认空间 17 配置全部完成，推荐配置满足全部 5 项护栏，验证运行通过。
- replay ≡ live：同配置在无 LLM-rerank 情况下结果集合与名次完全一致。
- 应用到生产：写入全量参数，KB 检索默认值生效于 AUTO/workflow 路径。

### 负例路径（主动触发）

- 数据集：非法 JSON、数组、小数分数、越界分数（-1/4）、空 query、`expected_empty` 与标注共存、超 1000 用例、超 2MB、标注 ID 不属于本 KB。
- 指标污染回归：加入 expected-empty 用例后 chunk nDCG 不变。
- 调优：空参数空间、单点空间（无候选可比）、`configs > 32`、`cases × configs > 5000`、数据集为空、活跃 sweep 期间再开一个、活跃期间改数据集。
- 执行器：rerank provider 401/429/超时、OpenSearch 停机（lexical 通道失败）、Qdrant 停机（dense 通道失败）、Celery 未启动（`evaluation_dispatch_failed`）、任务中途取消、`_weighted_rrf` 缓存污染断言。
- 验证：人为注入偏差使 `|Δ| > tolerance` → `drift=True`、推荐撤回、应用被阻止。
- 权限：`evaluate` 缺失 → 调优接口 403；`update` 缺失 → apply 403；dashboard 与 platform 两条路由各自独立验证。

### 回归范围

- 全部现有检索路径（AUTO RAG、Agentic、AgentService、workflow 知识检索节点、`/search` 接口）在未设置 KB 默认参数时行为不变。
- 现有 `retrieval-lab.test.tsx` 在阶段 5 拆分后零修改通过。
- 现有评估接口与 Celery 任务的既有测试全部通过。
- 混合检索 rollout 开关（`RETRIEVAL_HYBRID_KILL_SWITCH`、`retrieval_hybrid_mode`、shadow）行为不受影响。

---

## 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| replay 与生产路径产生偏差 | 推荐配置在生产不复现，信任崩塌 | 强制生产路径验证运行 + 容差门槛 + drift 撤回；replay≡live 等价性单测 |
| LLM listwise rerank 破坏单对确定性 | replay 结果错误 | 检测适配器类型，自动降级 live，前端显式提示 |
| 池化标注偏差 | 调优在自己造的池上过拟合 | 用差异化配置建池；文档与 UI 说明"池内召回"；跨数据集不比绝对值 |
| 小数据集上的噪声被当成改进 | 推荐错误配置 | 改进门槛 + 逐用例胜负计数双条件；数据集 < 10 个有效用例时前端警告 |
| rerank 调用产生真实费用 | 意外账单 | 成本预估前置展示、配置数硬上限、rerank 分数缓存、并发上限 4 |
| 扩展 `KnowledgeBaseSettings` 影响所有检索调用方 | 生产检索行为漂移 | 新字段全部可选且默认 `None`；优先级链保持"调用方 > KB 默认 > 系统默认"；未设置时行为逐字节不变的回归测试 |
| Celery 未启动导致 sweep 永久 pending | 用户体验卡死 | 沿用 `create_run` 的 dispatch 失败即置 failed 模式；sweep 增加创建后 dispatch 校验 |
| 前端单文件继续膨胀 | 不可维护 | 阶段 5 先拆分再加功能，新功能各自独立文件 |
| 一次性交付过大 | 评审困难、回滚粒度粗 | 12 个阶段各自独立可发布；阶段 2/3/4 单独就有价值（修正确性 + 让参数可落地） |

### 回滚方案

- 阶段 2/3/4：纯增量，回滚即回滚代码（`KnowledgeBaseSettings` 新字段为可选，遗留数据无需清理）。
- 阶段 8/9：`evaluation_sweeps` 表与 `evaluation_runs` 新列均为附加；回滚代码后旧逻辑忽略新列即可运行，无需 DDL 回退。
- 阶段 10/11：前端功能位于独立子页签，可通过不渲染该页签快速下线。
- 调优本身不改变生产检索行为——只有用户显式点击「应用到生产」才写 KB settings，且该写入是常规 KB 更新，可用现有 KB 编辑界面还原。

---

## 工作量估算

| 阶段 | 人日 |
|---|---|
| 1 设计文档与索引 | 0.5 |
| 2 指标正确性 | 0.5 |
| 3 KB 检索默认参数落地 | 1.5 |
| 4 用例增量 CRUD 与导出 | 1.0 |
| 5 组件拆分（含两个小缺陷修复） | 1.0 |
| 6 标注工作台 | 2.0 |
| 7 数据集质量面板 | 0.5 |
| 8 调优后端 | 1.5 |
| 9 调优执行器 | 2.5 |
| 10 调优前端 | 2.0 |
| 11 LLM 预标注（可选） | 1.5 |
| 12 i18n/类型/文档/验证 | 1.0 |
| **合计** | **15.5**（不含阶段 11 为 14.0） |

最小可用切片：阶段 1–4 + 6 + 8–10（约 11 人日）即可端到端跑通"标注 → 调优 → 应用"。
