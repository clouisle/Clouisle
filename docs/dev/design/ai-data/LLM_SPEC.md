# Clouisle LLM 调用规范

## 1. 概述

本文档定义了 Clouisle 项目中统一的 LLM（大语言模型）调用规范，支持多种模型类型和供应商。

### 1.1 设计目标

- **供应商无关**：统一抽象不同供应商的 API 差异
- **类型全面**：支持 Chat、Embedding、图像生成、视频生成、语音等
- **易于使用**：简洁的调用接口，合理的默认值
- **可扩展**：便于新增供应商和模型类型
- **可观测**：统一的日志、计量和错误处理

### 1.2 技术选型

| 模型类型 | 技术方案 | 说明 |
|----------|----------|------|
| Chat / Embedding / Rerank | LangChain | 生态丰富，支持 50+ 供应商 |
| Image / Video / Audio | 自研适配器 | LangChain 支持不完善 |
| Tools / MCP | 自研 Registry + 官方 `mcp` SDK | 工具注册表见 `app/llm/tools/`，MCP 客户端为 `tools/mcp_client.py` |
| Agent | LangGraph | 复杂工作流支持 |

---

## 2. 架构设计

```
┌─────────────────────────────────────────────────────────────────────┐
│                         应用层 (Application)                         │
│   Chat Agent | RAG | 图片生成 | 视频生成 | 语音合成 | 语音识别        │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Clouisle Model Service                          │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                      ModelManager                            │    │
│  │  - 从数据库加载模型配置                                        │    │
│  │  - 根据类型分发到对应的 Provider                               │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                │                                     │
│         ┌──────────────────────┼──────────────────────┐             │
│         ▼                      ▼                      ▼             │
│  ┌─────────────┐       ┌─────────────┐       ┌─────────────┐        │
│  │ ChatProvider│       │GenProvider  │       │AudioProvider│        │
│  │ (LangChain) │       │ (自研适配)   │       │ (自研适配)   │        │
│  │             │       │             │       │             │        │
│  │ - Chat      │       │ - Image     │       │ - TTS       │        │
│  │ - Embedding │       │ - Video     │       │ - STT       │        │
│  │ - Rerank    │       │             │       │             │        │
│  └─────────────┘       └─────────────┘       └─────────────┘        │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Provider Adapters                             │
│                                                                      │
│  Chat/Embedding (LangChain):                                         │
│  ├── OpenAI, Anthropic, Google, Azure, DeepSeek, Moonshot, Ollama   │
│                                                                      │
│  Image Generation (自研):                                            │
│  ├── OpenAI DALL-E, Stability AI, Midjourney                        │
│                                                                      │
│  Video Generation (自研):                                            │
│  ├── Runway Gen-3, Pika, Luma, Kling (可灵)                         │
│                                                                      │
│  Audio (自研):                                                       │
│  ├── OpenAI TTS/Whisper, Azure, ElevenLabs                          │
│                                                                      │
│  Decision (自研):                                                    │
│  └── TypeSafe AI (System One, POST /v1/systemone)                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. 模型类型

| 类型 | 代码 | 输入 | 输出 | 示例供应商 |
|------|------|------|------|-----------|
| 对话 | `chat` | 文本/图片 | 文本 | OpenAI, Anthropic, DeepSeek |
| 嵌入 | `embedding` | 文本 | 向量 | OpenAI, Cohere |
| 重排序 | `rerank` | Query + Docs | 分数 | Cohere, Jina |
| 决策 | `decision` | state + 类型化问题 | 类型化答案 + 概率 | TypeSafe AI |
| 语音合成 | `tts` | 文本 | 音频 | OpenAI, Azure |
| 语音识别 | `stt` | 音频 | 文本 | OpenAI Whisper |
| 文生图 | `text_to_image` | 文本 | 图片 | DALL-E, Midjourney |
| 文生视频 | `text_to_video` | 文本 | 视频 | Runway, Pika, Kling |
| 图生视频 | `image_to_video` | 图片+文本 | 视频 | Runway, Luma, Kling |

---

## 4. 核心接口

### 4.1 ModelManager

```python
from app.llm import model_manager

class ModelManager:
    """统一模型管理器"""
    
    # ========== Chat (LangChain) ==========
    async def chat(messages, model_id=None, tools=None, **kwargs) -> ChatResponse
    async def chat_stream(messages, model_id=None, **kwargs) -> AsyncIterator[ChatStreamChunk]
    async def get_chat_model(model_id=None) -> BaseChatModel
    
    # ========== Embedding (LangChain) ==========
    async def embed(texts, model_id=None) -> list[list[float]]
    async def get_embedding_model(model_id=None) -> Embeddings
    
    # ========== Image Generation ==========
    async def generate_image(request, model_id=None) -> ImageGenerationResponse
    
    # ========== Video Generation ==========
    async def generate_video(request, model_id=None) -> VideoGenerationResponse
    async def get_video_status(task_id, model_id=None) -> VideoGenerationResponse
    
    # ========== Audio ==========
    async def text_to_speech(request, model_id=None) -> TTSResponse
    async def speech_to_text(request, model_id=None) -> STTResponse

    # ========== Decision ==========
    async def decide(request, model_id=None) -> DecisionResponse
```

### 4.2 使用示例

```python
from app.llm import model_manager
from app.llm.types import (
    ImageGenerationRequest,
    VideoGenerationRequest,
    TTSRequest,
    STTRequest,
    ImageContent,
    AudioContent,
    DecisionRequest,
    DecisionQuestion,
)

# ========== Chat ==========
response = await model_manager.chat(
    messages=[{"role": "user", "content": "Hello!"}],
    model_id="gpt-4o",
)

# 流式对话
async for chunk in model_manager.chat_stream(messages):
    print(chunk.delta.content, end="")

# ========== Embedding ==========
embeddings = await model_manager.embed(["text1", "text2"])

# ========== 图片生成 ==========
result = await model_manager.generate_image(
    ImageGenerationRequest(
        prompt="A cat in space",
        width=1024,
        height=1024,
    ),
    model_id="dall-e-3",
)

# ========== 视频生成 ==========
result = await model_manager.generate_video(
    VideoGenerationRequest(
        prompt="A serene lake at sunset",
        duration=5.0,
    ),
    model_id="runway-gen3",
)

# 图生视频
result = await model_manager.generate_video(
    VideoGenerationRequest(
        prompt="Camera zooms out",
        image=ImageContent(url="https://example.com/image.jpg"),
    ),
)

# ========== TTS ==========
audio = await model_manager.text_to_speech(
    TTSRequest(text="Hello!", voice="nova"),
)

# ========== STT ==========
transcript = await model_manager.speech_to_text(
    STTRequest(audio=AudioContent(file_path="audio.mp3")),
)

# ========== Decision（类型化决策，非生成式） ==========
decision = await model_manager.decide(
    DecisionRequest(
        state="用户申请退款 200 元，订单已超过 7 天",
        questions={
            "refund": DecisionQuestion(
                type="choice",
                instructions="是否批准该退款申请？",
                criteria={"approve": None, "reject": None},
            )
        },
    ),
    model_id="jev-1.13.0",
)
answer = decision.answers["refund"]
answer.choice          # 概率最高的选项
answer.probabilities   # 每个选项/等级的概率分布
answer.confidence      # 由分布推导的确定性（noul 不返回）
```

---

## 5. 数据类型

### 5.1 媒体内容

```python
class MediaContent(BaseModel):
    url: str | None = None           # 远程 URL
    base64: str | None = None        # Base64 编码
    file_path: str | None = None     # 本地文件路径

class ImageContent(MediaContent):
    width: int | None = None
    height: int | None = None
    format: str = "png"

class VideoContent(MediaContent):
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    format: str = "mp4"

class AudioContent(MediaContent):
    duration: float | None = None
    format: str = "mp3"
```

### 5.2 Chat 类型

```python
class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

class Message(BaseModel):
    role: MessageRole
    content: str | list[ContentPart]
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None

class ChatRequest(BaseModel):
    messages: list[Message]
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stream: bool = False
    tools: list[Tool] | None = None

class ChatResponse(BaseModel):
    id: str
    model: str
    content: str | None
    tool_calls: list[ToolCall] | None
    finish_reason: FinishReason
    usage: Usage
```

### 5.3 生成类型

```python
class ImageGenerationRequest(BaseModel):
    prompt: str
    negative_prompt: str | None = None
    width: int = 1024
    height: int = 1024
    num_images: int = 1
    style: str | None = None
    seed: int | None = None

class VideoGenerationRequest(BaseModel):
    prompt: str
    image: ImageContent | None = None  # 图生视频时提供
    duration: float = 5.0
    aspect_ratio: str = "16:9"
    motion_intensity: float = 0.5
    seed: int | None = None

class TTSRequest(BaseModel):
    text: str
    voice: str = "alloy"
    speed: float = 1.0
    format: str = "mp3"

class STTRequest(BaseModel):
    audio: AudioContent
    language: str | None = None
    prompt: str | None = None
```

### 5.4 决策类型

```python
DecisionQuestionType = Literal["choice", "score", "noul"]

class DecisionQuestion(BaseModel):
    type: DecisionQuestionType            # choice / score / noul
    instructions: str | dict | list       # 要评估的问题
    criteria: dict[str, Any] | list[Any] | None = None

class DecisionRequest(BaseModel):
    state: str | dict | list              # 被评估的内容
    questions: dict[str, DecisionQuestion]  # 以 id 为键，便于回读答案
    model: str | None = None              # 覆盖供应商配置的模型

class DecisionAnswer(BaseModel):
    type: DecisionQuestionType
    choice: str | None = None             # choice：概率最高的选项
    probabilities: dict[str, float] | None = None  # 每个选项/等级的概率
    confidence: float | None = None       # 由分布推导的确定性（noul 不返回）
    score: float | None = None            # score：按概率加权的位置
    legend: dict[str, str] | None = None  # score：等级编号 -> 描述
    noul: float | None = None             # noul：答案为 yes 的概率

class DecisionResponse(BaseModel):
    model: str                            # 产生答案的模型
    answers: dict[str, DecisionAnswer]    # 以问题 id 为键
    usage: Usage
```

---

## 6. 错误处理

```python
class LLMError(Exception):
    """LLM 调用基础异常"""
    code: str
    message: str
    provider: str
    model: str

class AuthenticationError(LLMError):
    """认证失败"""

class RateLimitError(LLMError):
    """速率限制"""
    retry_after: int | None

class ContextLengthError(LLMError):
    """上下文超长"""

class ContentFilterError(LLMError):
    """内容审核拦截"""

class ModelNotFoundError(LLMError):
    """模型不存在"""

class ProviderError(LLMError):
    """供应商服务异常"""
```

---

## 7. 文件结构

```
backend/app/llm/
├── __init__.py                    # 导出 model_manager
├── manager.py                     # ModelManager 主类
├── errors.py                      # 统一异常
├── token_counter.py               # token 计数（tiktoken）
├── types/
│   ├── __init__.py
│   ├── base.py                    # 基础类型
│   ├── chat.py                    # Chat 类型
│   ├── embedding.py               # Embedding 类型
│   ├── rerank.py                  # 重排类型
│   ├── image.py                   # 图像生成类型
│   ├── video.py                   # 视频生成类型
│   ├── audio.py                   # 音频类型
│   └── decision.py                # 决策类型（choice / score / noul）
├── adapters/
│   ├── __init__.py
│   ├── chat/                      # Chat 适配器（LangChain）
│   │   ├── base.py / factory.py
│   │   ├── openai_adapter.py / openai_compatible_adapter.py
│   │   ├── anthropic_adapter.py / gemini_adapter.py
│   │   ├── deepseek_adapter.py / moonshot_adapter.py
│   │   ├── ollama_adapter.py / xai_adapter.py
│   │   ├── thinking.py / tool_call_accumulator.py
│   ├── embedding/                 # adapter.py + factory.py
│   ├── rerank/                    # base.py / factory.py / llm_adapter.py / openai_compatible_adapter.py
│   ├── image/                     # base.py + openai / openai_responses / google /
│   │                              #   stability / minimax / luma / runway / siliconflow / volcengine
│   ├── video/                     # base.py + dashscope / kling / luma / minimax /
│   │                              #   pika / runway / siliconflow / volcengine
│   ├── audio/                     # base.py + openai_tts / openai_stt / minimax_tts /
│   │                              #   volcengine_tts / volcengine_generation
│   ├── decision/                  # base.py / factory.py / typesafe_adapter.py
│   ├── *_client.py                # 供应商直连客户端（runway / luma / pika / kling /
│   │                              #   minimax / dashscope_video / siliconflow / volcengine）
│   └── media_utils.py
└── tools/                         # 工具系统
    ├── __init__.py
    ├── registry.py                # Tool Registry
    ├── executors.py
    ├── mcp_client.py              # MCP 客户端（基于官方 mcp SDK，无独立 llm/mcp/ 包）
    ├── memory_tools.py            # 记忆工具
    ├── interaction.py
    ├── bash.py / bash_output.py
    ├── sandbox.py / sandbox_files.py / sandbox_paths.py
    └── builtin/                   # 内置工具（含数据库连接器，见 TOOL_SYSTEM_SPEC）
```

没有顶层 `adapters/base.py`、`adapters/image/midjourney.py`、
`adapters/audio/elevenlabs.py`、`llm/mcp/` 或 `llm/agents/` 包；Agent 循环
实现位于 `backend/app/services/agent_loop.py` 等模块。

---

## 8. 实现优先级

| 阶段 | 内容 | 状态 |
|------|------|------|
| **P0** | 类型定义 (types/) | 待实现 |
| **P0** | 错误类型 (errors.py) | 待实现 |
| **P0** | ModelManager 框架 | 待实现 |
| **P0** | Chat/Embedding (LangChain) | 待实现 |
| **P1** | OpenAI Image (DALL-E) | 待实现 |
| **P1** | OpenAI Audio (TTS/STT) | 待实现 |
| **P1** | Tool Registry + MCP | 待实现 |
| **P2** | Runway/Kling 视频 | 待实现 |
| **P2** | LangGraph Agent | 待实现 |
| **P3** | 更多供应商 | 待实现 |

---

## 9. 依赖包

以 `backend/pyproject.toml` 为唯一事实来源，当前相关 pin 为：

```toml
langchain>=1.3.9
langchain-core>=1.3.3
langchain-community>=0.4.1
langchain-openai>=1.2.1
langchain-anthropic>=1.4.6
langchain-google-genai>=4.2.1
google-genai>=1.72.0
langgraph>=1.1.6
mcp>=1.27.0            # MCP 客户端基于官方 mcp SDK，未使用 langchain-mcp-adapters
tiktoken>=0.12.0
```
