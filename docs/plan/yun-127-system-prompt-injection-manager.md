# YUN-127 标准化系统提示词注入管理器

## 背景与目标

### 问题
Agent 系统提示词的"条件注入"(沙箱指引、记忆指引、Markdown 规范、语言指令、用户输入请求格式)散落在多处,且实现分叉:

| 站点 | 路径 | 注入内容 | 状态 |
|---|---|---|---|
| `chat_context.py:_build_system_prompt` (L626) | 主聊天端点 | base+模板替换+Markdown+Memory+Sandbox+语言+UserInput | 生产主路径 |
| `agent.py:AgentService._build_messages` (L228) | 工作流 Agent 节点 | 仅 base+context,**无任何指令注入** | 生产,与主路径分叉 |
| `chat_helpers/message_builder.py:build_messages` (L10) | 无生产调用 | base+语言 | **死代码**,仅测试引用 |
| `build_system_prompt_with_language` | helper | 语言指令 | **两处重复且行为分叉**(config.py 多语言短句无去重;chat_context.py 仅 en/zh 严格指令带去重) |

**最关键的功能缺口**:工作流路径 `AgentService._get_agent_tools` 会装配并执行 `bash`/`read`/`edit`/`write`/`artifact` 与 skill 工具,但 `_build_messages` 从不注入 `SANDBOX_SYSTEM_INSTRUCTION`--模型拿到沙箱工具却没有任何 `/workspace` 别名、路径语义、工具用法的指引,只能靠猜。Markdown 输出规范、语言指令同理缺失。

### 目标
- 提取**统一的系统提示词注入管理器**,作为唯一组装入口
- 两条路径(主聊天端点 + 工作流 Agent)共用该管理器,**能力感知地对齐**
- 注入规则**声明式**管理(数据而非控制流),易于扩展
- 消除重复实现与死代码

### 成功标准
- 主聊天端点行为**完全不变**(现有测试全部通过)
- 工作流 Agent 获得:沙箱指引(修复 bug)+ Markdown 规范 + 语言指令
- 工作流 Agent **不**注入记忆/用户输入请求指引(因其未装配对应工具与前端解析器)
- 新增能力指引只需在声明式规则表加一条,不改组装函数
- 后端测试全绿,覆盖率达标

## 高层设计

新增 `backend/app/services/system_prompt.py` 作为唯一管理器,收纳:
1. 所有指令常量(`MARKDOWN_IMAGE_DISPLAY_INSTRUCTION`、`MEMORY_SYSTEM_INSTRUCTION`、`SANDBOX_SYSTEM_INSTRUCTION`、`LANGUAGE_INSTRUCTIONS`、`FILE_CONTENT_PLACEHOLDER`)
2. 所有 helper(`has_sandbox_tools`、`append_prompt_section`、`get_language_instruction`、`build_system_prompt_with_language`、`get_user_input_request_instruction`)
3. 声明式规则表 `SECTIONS`(每条规则:`name` / `applies(agent, mode)` / `transform(base, agent, locale)`)
4. 单一入口 `build_system_prompt(agent, *, base_prompt, user_message, variables, user_locale, invocation_mode)`

### 能力感知门控矩阵

| 指令 | 触发条件 | chat | workflow | 依据 |
|---|---|---|---|---|
| Markdown 规范 | 无条件 | ✅ | ✅ | 通用输出格式,无工具依赖 |
| Sandbox 指引 | `has_sandbox_tools(agent)`(查 tools_config) | ✅ | ✅ | 两路径都执行沙箱工具;**工作流补上即修复缺口** |
| 语言指令 | `build_system_prompt_with_language(base, locale)` | ✅ | ✅ | 通用;工作流需补 locale 入参 |
| Memory 指引 | `enable_memory and mode=="chat"` | ✅ | ❌ | 工作流未装配 memory 工具,注入会让模型调用不存在的 `search_memory` |
| UserInput 指引 | `enable_user_input_request and mode=="chat"` | ✅ | ❌ | 工作流无前端解析 `<user_input_request>` XML,注入会产出被忽略的 XML |

### 组装顺序(严格保持主路径现状)
base + 模板替换(`{{key}}`/`{{query}}`/`{{fileContent}}`) -> Markdown -> Memory -> Sandbox -> 语言 -> UserInput

### 调用关系
```text
chat.py -> chat_context._build_messages_with_file_content -> _build_system_prompt(agent, conversation, ...) [chat 适配器]
                                                              └─► system_prompt.build_system_prompt(..., mode="chat")

workflow/tool.py -> AgentService.chat/chat_stream(user_locale=...) -> _build_messages(user_locale=...)
                                                                       └─► system_prompt.build_system_prompt(..., mode="workflow")
```

- `chat_context._build_system_prompt` 保留为薄适配器:从 `conversation.variables` 取变量、固定 `mode="chat"`,调用统一入口。现有测试(直接调用它)无需改动。
- `chat_context` 重新导出迁移的常量/helper,保持现有 `from app.services.chat_context import ...` 的测试导入可用。
- `AgentService._build_messages` 改用统一入口(`mode="workflow"`),保留其 context 追加与 RAG 独立 SYSTEM 消息逻辑。
- 工作流 `tool.py` 执行器从 `run.triggered_by.locale` 派生 locale(沿用 orchestrator 已有模式),透传给 AgentService。

## 实施计划

### Stage 1: 创建统一管理器
- **新增文件**: `backend/app/services/system_prompt.py`
- **具体逻辑**: 迁移常量与 helper(行为以 chat_context 生产版本为准);定义 `PromptSection` dataclass 与 `SECTIONS` 规则表;实现 `build_system_prompt()` 入口
- **验证**: 单元测试覆盖各规则门控(含 workflow 模式)

### Stage 2: 主聊天端点委托
- **修改文件**: `backend/app/services/chat_context.py`
- **具体逻辑**: 删除迁移走的常量/helper 定义,改为从 `system_prompt` 导入并重新导出;`_build_system_prompt` 改为薄适配器;`FILE_CONTENT_PLACEHOLDER` 从 `system_prompt` 导入
- **验证**: `test_chat_context_sandbox_prompt.py` 等现有测试全绿

### Stage 3: 工作流路径对齐
- **修改文件**: `backend/app/services/agent.py`、`backend/app/services/workflow/executors/tool.py`
- **具体逻辑**: `AgentService.chat/chat_stream` 增加 `user_locale` 参数;`_build_messages` 用 `build_system_prompt(mode="workflow")` 替换手工组装,保留 RAG 独立 SYSTEM 消息;`tool.py` 从 `run.triggered_by` 派生 locale 透传
- **验证**: 新增测试断言工作流模式注入沙箱/Markdown/语言、不注入 Memory/UserInput

### Stage 4: 清理死代码与重复实现
- **删除文件**: `chat_helpers/message_builder.py`(死代码)
- **修改文件**: `chat_helpers/config.py`(删除分叉的 `get_language_instruction`/`build_system_prompt_with_language`)、`chat_helpers/__init__.py`(移除对应导出)
- **验证**: 无生产引用断裂

### Stage 5: 测试与验证
- **修改文件**: `test_chat_helpers_behavior_unit.py`(移除 message_builder 测试与 config 语言断言,保留 streaming 测试)
- **新增测试**: 工作流模式门控、locale 透传
- **验证**: `uv run pytest` 全绿 + `uv run python scripts/check_coverage.py` 达标

## 测试策略

### Happy path
- 主聊天端点:沙箱工具->注入沙箱指引;enable_memory->注入记忆指引;空 base->仍有 Markdown+语言
- 工作流:沙箱工具->注入沙箱指引(新修复);locale 透传->语言指令正确

### Error/negative path
- 工作流:enable_memory=True->**不**注入记忆指引
- 工作流:enable_user_input_request=True->**不**注入 UserInput 指引
- 无沙箱工具->不注入沙箱指引

### 回归范围
- 主聊天端点系统提示词**字节级不变**(现有 `test_chat_context_*` 全绿)
- 工作流 Agent 输出:新增 Markdown/语言/沙箱指引(预期行为变更,修复缺口)
- `chat_helpers` 公共 API:移除死代码导出,确认无生产引用

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 工作流 Agent 现在始终带系统消息(空 prompt 也注入 Markdown+语言) | 与主路径对齐的预期行为;语言由触发用户 locale 驱动,默认 en |
| `enable_memory`/`enable_user_input_request` 的工作流 Agent 不注入对应指引 | 正确行为:工作流未装配对应工具/解析器;若未来补齐工具,只需放宽规则门控 |
| chat_context 测试直接导入迁移符号 | 重新导出保持导入路径不变 |
| 覆盖率门禁 | workflow 模式新分支需测试覆盖 |

### 回滚
改动按 Stage 提交,每 Stage 可独立回滚。Stage 1(新文件)无副作用;Stage 2/3 为行为切换点。
