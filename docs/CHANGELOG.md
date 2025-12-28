# 更新日志 (Changelog)

本文档记录项目的所有重要变更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [Unreleased]

### 新增 (Added)

#### 应用模块 - Agent 编排页面重构

##### 布局重构

将 Agent 配置页面从传统的 Tab 表单布局重构为现代化三栏布局：

- **左侧边栏** (`agent-sidebar.tsx`):
  - Agent 图标、名称和类型标签显示
  - 悬停时图标变为返回箭头，点击返回应用列表
  - 导航菜单：编排、访问 API、日志与标注、监控

- **中间主内容区** (`agent-orchestration-form.tsx`):
  - 提示词编辑器：带 AI 生成按钮、字符计数
  - 变量配置：可折叠面板，支持添加自定义变量
  - 知识库关联：显示已关联知识库，元数据过滤开关
  - 工具配置：工具列表与启用状态开关
  - 视觉能力：可折叠面板，图片理解功能开关

- **右侧预览面板** (`agent-preview-panel.tsx`):
  - 调试与预览聊天窗口
  - 实时对话测试
  - 功能状态指示器

- **顶部工具栏** (`agent-toolbar.tsx`):
  - Agent 设置按钮（打开侧边抽屉）
  - 模型选择器下拉菜单（带模型图标和标签）
  - 模型参数调整对话框（温度、最大 Token）
  - 发布/取消发布下拉菜单

- **设置抽屉** (`agent-settings-drawer.tsx`):
  - 基础信息配置：图标、名称、描述
  - 开场消息和建议问题
  - 可见性设置（私有/团队）

##### 导航整合

- 将「智能 Agent」和「工作流」聚合到「应用」导航项下
- 更新 `platform-header.tsx`：移除独立的 Agents 导航，使用 AppWindow 图标
- 更新路由：`/app/workspace` → `/app/apps`

##### 应用列表页面 (`apps/page.tsx`)

- 统一的应用列表，支持类型筛选标签（全部/Agent/工作流）
- 简化的创建对话框：只需输入名称和描述，选择应用类型
- 应用卡片：显示类型标签、状态徽章、操作菜单

##### 后端修复

- 修复 `build_agent_out()` 函数：手动构建字典避免 Tortoise ORM ForeignKey 字段的 Pydantic 验证错误
- 修复 `build_agent_list_out()` 函数：同样的 QuerySet 序列化问题
- 正确处理 `model_id` UUID 转字符串、枚举值提取

##### 新增 UI 组件

- 通过 shadcn/ui 安装 `Slider` 组件
- 通过 shadcn/ui 安装 `RadioGroup` 组件

##### 国际化

- 新增 `apps` 命名空间翻译（中文/英文）
- 包含应用类型、创建流程、状态提示等文案

### 修复 (Fixed)

- Agent 详情 API 验证错误：`model.name`、`model.provider`、`model.model_id` 字段缺失
- 嵌套按钮水合错误：移除 DropdownMenuTrigger 的 `asChild` 属性
- base-ui 组件兼容性：Tooltip、Dialog、Dropdown 等组件不支持 `asChild`，改用直接样式
- Select 组件 `onValueChange` 类型：处理 `null` 值情况
- Slider `onValueChange` 类型：处理 `number | readonly number[]` 联合类型

---

#### 知识库模块 - 完整实现 (#12)

##### 后端 (Backend)

- **知识库 CRUD API**: 完整的知识库管理接口，支持创建、查询、更新、删除
- **文档管理**: 支持多种文件格式上传 (PDF, DOCX, TXT, MD, HTML, CSV, XLSX, JSON, PPTX)
- **URL 导入**: 支持从网页 URL 导入内容到知识库
- **文档处理流水线**:
  - 文档解析与文本提取
  - 智能分块 (支持自定义 chunk_size, chunk_overlap, separator)
  - 分块预览功能，确认后再入库
  - 文本清洗选项
- **向量化与存储**:
  - 集成 embedding 模型进行文档向量化
  - 支持自定义 embedding 模型选择
- **三种搜索模式**:
  - `vector`: 语义向量搜索，基于 embedding 相似度
  - `fulltext`: 全文关键词搜索，集成 jieba 中文分词
  - `hybrid`: 混合搜索，使用 RRF (Reciprocal Rank Fusion) 算法融合结果
- **搜索性能优化**: 数据库层 ILIKE 预过滤，大幅提升搜索速度
- **文档下载 API**: 支持下载原始上传文件，返回 `file_path`、`source_url`、`error_message` 字段
- **分块编辑 API**: 支持对已处理文档的分块进行增删改

##### 前端 (Frontend)

- **知识库列表页**:
  - 支持搜索、状态筛选
  - 批量选择与批量删除
  - 分页浏览
- **知识库详情页**:
  - 统计卡片 (文档数、分块数、Token 数、处理状态)
  - 文档列表与管理
- **文档上传**:
  - 拖拽上传支持
  - 多文件批量上传
  - 文件类型验证
  - 上传进度显示
- **文档处理预览**:
  - 单文档/批量文档分块预览
  - 分块参数实时调整
  - 分块内容编辑、删除、新增
  - 预览确认后再提交处理
- **搜索测试页面** (后台 + 中台):
  - 三种搜索模式切换
  - 搜索结果可折叠卡片，显示相似度分数
  - 底部圆角胶囊式搜索栏，现代 AI 聊天风格
  - 高级设置弹出菜单 (Popover): 检索方式、top_k、threshold
  - 支持中文输入法 (IME) 组合状态检测，避免回车误触发
  - 相似度阈值支持小数输入 (0-1)
- **文档操作**:
  - 下载原始文件 (带 Authorization 鉴权)
  - 查看源链接 (URL 类型文档)
  - 显示处理失败错误信息
  - 重新处理
  - 删除文档
  - 查看分块详情

##### 新增 UI 组件

- `ToggleGroup`: 搜索模式切换组件
- `Collapsible`: 可折叠面板组件
- `Progress`: 进度条组件
- `Popover`: 弹出菜单组件 (用于高级设置)

##### 依赖更新

- 后端新增 `jieba>=0.42.1` - 中文分词支持

### 修复 (Fixed)

- 搜索性能问题：从 11 秒优化到毫秒级响应
- 中文搜索分词问题：使用 jieba 替代简单字符分割
- 搜索测试页面布局：搜索栏固定在底部，不被内容挤压
- 文档上传路径计算错误：修正 dirname 层级从 5 改为 4
- 中文输入法回车误触发：添加 `e.nativeEvent.isComposing` 检测
- 后台 SidebarInset 圆角被遮挡：底部栏添加 `md:rounded-b-xl`
- 中台搜索栏 sticky 定位失效：使用 `calc(100vh - 64px)` 显式高度

---

## 贡献指南

在提交代码时，请在提交信息中关联相关 Issue，格式如：

```
feat(knowledge-base): 实现知识库搜索功能

- 添加向量搜索、全文搜索、混合搜索三种模式
- 集成 jieba 中文分词

Closes #12
```
