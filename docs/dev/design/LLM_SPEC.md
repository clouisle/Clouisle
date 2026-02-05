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
| Tools / MCP | LangChain + langchain-mcp-adapters | 原生支持 |
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
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. 模型类型

| 类型 | 代码 | 输入 | 输出 | 示例供应商 |
|------|------|------|------|-----------|
| 对话 | `chat` | 文本/图片 | 文本 | OpenAI, Anthropic, DeepSeek |
| 嵌入 | `embedding` | 文本 | 向量 | OpenAI, Cohere |
| 重排序 | `rerank` | Query + Docs | 分数 | Cohere, Jina |
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
├── types/
│   ├── __init__.py
│   ├── base.py                    # 基础类型
│   ├── chat.py                    # Chat 类型
│   ├── image.py                   # 图像生成类型
│   ├── video.py                   # 视频生成类型
│   └── audio.py                   # 音频类型
├── adapters/
│   ├── __init__.py
│   ├── base.py                    # 适配器基类
│   ├── chat/                      # Chat 适配器 (LangChain)
│   │   ├── __init__.py
│   │   └── factory.py
│   ├── image/                     # 图像生成适配器
│   │   ├── __init__.py
│   │   ├── openai.py
│   │   ├── stability.py
│   │   └── midjourney.py
│   ├── video/                     # 视频生成适配器
│   │   ├── __init__.py
│   │   ├── runway.py
│   │   ├── pika.py
│   │   ├── luma.py
│   │   └── kling.py
│   └── audio/                     # 音频适配器
│       ├── __init__.py
│       ├── openai_tts.py
│       ├── openai_stt.py
│       └── elevenlabs.py
├── tools/                         # 工具系统
│   ├── __init__.py
│   ├── registry.py
│   └── builtin/
├── mcp/                           # MCP 集成
│   ├── __init__.py
│   └── manager.py
├── agents/                        # Agent 系统
│   ├── __init__.py
│   └── react.py
└── errors.py                      # 统一异常
```

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

```toml
# LangChain 核心
langchain = "^0.3"
langchain-core = "^0.3"
langchain-community = "^0.3"

# 供应商支持
langchain-openai = "^0.2"
langchain-anthropic = "^0.2"
langchain-google-genai = "^2.0"

# Agent 框架
langgraph = "^0.2"

# MCP 支持
langchain-mcp-adapters = "^0.1"
```
