# nanobot 架构设计文档

## 目录

1. [项目概述](#项目概述)
2. [整体架构](#整体架构)
3. [核心模块详解](#核心模块详解)
4. [数据流分析](#数据流分析)
5. [扩展机制](#扩展机制)
6. [配置体系](#配置体系)
7. [部署架构](#部署架构)

---

## 项目概述

nanobot 是一个**轻量级 AI Agent 框架**，仅用约 5,000 行代码实现了 OpenClaw 的核心能力。它采用**模块化、事件驱动**的架构设计，支持多聊天渠道、多 LLM 提供商和丰富的工具生态。

### 核心特性

| 特性 | 说明 |
|:---|:---|
| **多渠道支持** | Telegram、WhatsApp、Discord 等 |
| **多模型支持** | OpenAI、Anthropic、Gemini、OpenRouter、本地模型等 |
| **工具系统** | 文件操作、Shell 执行、Web 搜索、子代理等 |
| **记忆系统** | 长期记忆 + 每日笔记 |
| **技能系统** | 可插拔的技能（Skills）机制 |
| **会话管理** | 持久化的对话历史 |

---

## 整体架构

### 架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户交互层                                       │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐                │
│  │ Telegram  │  │ WhatsApp  │  │  Discord  │  │   CLI     │                │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘                │
└────────┼──────────────┼──────────────┼──────────────┼────────────────────────┘
         │              │              │              │
         └──────────────┴──────────────┴──────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              渠道适配层 (Channels)                            │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                     ChannelManager                                    │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────────┐  │  │
│  │  │   Telegram   │  │   WhatsApp   │  │        BaseChannel         │  │  │
│  │  │   Channel    │  │   Channel    │  │       (抽象基类)            │  │  │
│  │  └──────┬───────┘  └──────┬───────┘  └─────────────┬──────────────┘  │  │
│  └─────────┼─────────────────┼────────────────────────┼─────────────────┘  │
└────────────┼─────────────────┼────────────────────────┼──────────────────────┘
             │                 │                        │
             └─────────────────┴────────────────────────┘
                              │
                              ▼ InboundMessage / OutboundMessage
┌─────────────────────────────────────────────────────────────────────────────┐
│                              消息总线层 (Message Bus)                         │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                          MessageBus                                   │  │
│  │  ┌─────────────────┐         ┌─────────────────┐                     │  │
│  │  │  Inbound Queue  │ ◄────── │  渠道适配层      │                     │  │
│  │  │  (渠道 → Agent) │         │                 │                     │  │
│  │  └────────┬────────┘         └─────────────────┘                     │  │
│  │           │                                                         │  │
│  │  ┌────────▼────────┐         ┌─────────────────┐                     │  │
│  │  │  Outbound Queue │ ──────► │  渠道适配层      │                     │  │
│  │  │  (Agent → 渠道)  │         │                 │                     │  │
│  │  └─────────────────┘         └─────────────────┘                     │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Agent 核心层                                    │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         AgentLoop                                     │  │
│  │                                                                       │  │
│  │   ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐  │  │
│  │   │   Context   │    │   Session   │    │       ToolRegistry      │  │  │
│  │   │   Builder   │    │   Manager   │    │                         │  │  │
│  │   └──────┬──────┘    └──────┬──────┘    └────────────┬────────────┘  │  │
│  │          │                  │                       │                │  │
│  │          └──────────────────┼───────────────────────┘                │  │
│  │                             │                                        │  │
│  │   ┌─────────────────────────▼────────────────────────────┐          │  │
│  │   │                    ReAct Loop                        │          │  │
│  │   │  1. 接收消息 → 2. 构建上下文 → 3. LLM 调用           │          │  │
│  │   │  4. 工具执行 → 5. 返回结果   (循环直到完成)          │          │  │
│  │   └─────────────────────────┬────────────────────────────┘          │  │
│  └─────────────────────────────┼───────────────────────────────────────┘  │
└────────────────────────────────┼───────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              工具与能力层                                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  FileSystem │  │    Shell    │  │    Web      │  │      Subagent       │ │
│  │    Tools    │  │   (exec)    │  │  (search)   │  │      (spawn)        │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────┘ │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │    Read     │  │   Execute   │  │    Fetch    │  │   Background Task   │ │
│  │    Write    │  │   Command   │  │    Page     │  │                     │ │
│  │    Edit     │  │             │  │             │  │                     │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              基础设施层                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │    LLM      │  │   Memory    │  │   Skills    │  │       Cron          │ │
│  │  Providers  │  │    Store    │  │   Loader    │  │     (定时任务)       │ │
│  │             │  │             │  │             │  │                     │ │
│  │ - OpenAI    │  │ - Long-term │  │ - Discovery │  │ - Scheduled Jobs    │ │
│  │ - Claude    │  │ - Daily     │  │ - Loading   │  │ - Reminders         │ │
│  │ - Gemini    │  │             │  │             │  │                     │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 分层说明

| 层次 | 职责 | 核心组件 |
|:---|:---|:---|
| **用户交互层** | 各种聊天渠道接入 | Telegram、WhatsApp、Discord、CLI |
| **渠道适配层** | 协议转换、消息格式化 | ChannelManager、BaseChannel |
| **消息总线层** | 解耦渠道与核心、异步通信 | MessageBus、Inbound/Outbound Queue |
| **Agent 核心层** | 消息处理、决策循环、上下文管理 | AgentLoop、ContextBuilder、SessionManager |
| **工具与能力层** | 具体能力实现 | ToolRegistry、各类 Tool |
| **基础设施层** | LLM 调用、记忆、技能、定时任务 | Providers、MemoryStore、SkillsLoader、Cron |

---

## 核心模块详解

### 1. Agent 核心模块 (`nanobot/agent/`)

#### 1.1 AgentLoop - 主循环

```python
class AgentLoop:
    """Agent 主循环：消息处理的核心引擎"""
    
    # 核心组件
    context: ContextBuilder      # 上下文构建
    sessions: SessionManager     # 会话管理
    tools: ToolRegistry          # 工具注册
    subagents: SubagentManager   # 子代理管理
    
    async def run(self):
        """主循环：持续消费消息并处理"""
        while self._running:
            msg = await self.bus.consume_inbound()
            response = await self._process_message(msg)
            await self.bus.publish_outbound(response)
```

**ReAct 循环实现**：

```python
async def _process_message(self, msg: InboundMessage):
    """处理单条消息的 ReAct 循环"""
    
    # 1. 获取会话和构建上下文
    session = self.sessions.get_or_create(msg.session_key)
    messages = self.context.build_messages(
        history=session.get_history(),
        current_message=msg.content
    )
    
    # 2. ReAct 循环（最大迭代次数限制）
    for iteration in range(self.max_iterations):
        # 调用 LLM
        response = await self.provider.chat(
            messages=messages,
            tools=self.tools.get_definitions()
        )
        
        if response.has_tool_calls:
            # 执行工具调用
            for tool_call in response.tool_calls:
                result = await self.tools.execute(
                    tool_call.name, 
                    tool_call.arguments
                )
                messages = self.context.add_tool_result(...)
        else:
            # 无工具调用，返回最终响应
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=response.content
            )
```

#### 1.2 ContextBuilder - 上下文构建

```python
class ContextBuilder:
    """构建发送给 LLM 的完整上下文"""
    
    def build_system_prompt(self) -> str:
        """构建系统提示词，包含：
        1. 核心身份信息
        2. Bootstrap 配置文件（AGENTS.md, SOUL.md 等）
        3. 记忆内容
        4. 技能信息（渐进式加载）
        """
        parts = []
        parts.append(self._get_identity())           # 身份
        parts.append(self._load_bootstrap_files())   # 配置
        parts.append(self.memory.get_memory_context())  # 记忆
        parts.append(self.skills.load_skills_for_context(always_skills))  # 技能
        return "\n\n---\n\n".join(parts)
```

**渐进式技能加载**：
- **Always Skills**：完整加载到上下文（如核心工具说明）
- **Available Skills**：只显示摘要，Agent 按需读取 SKILL.md

#### 1.3 工具系统 (`nanobot/agent/tools/`)

```python
class Tool(ABC):
    """工具抽象基类"""
    
    @property
    @abstractmethod
    def name(self) -> str: ...           # 工具名称
    
    @property
    @abstractmethod
    def description(self) -> str: ...    # 功能描述
    
    @property
    @abstractmethod
    def parameters(self) -> dict: ...    # JSON Schema 参数定义
    
    @abstractmethod
    async def execute(self, **kwargs) -> str: ...  # 执行逻辑
```

**内置工具清单**：

| 工具 | 功能 | 安全特性 |
|:---|:---|:---|
| `read_file` | 读取文件 | 路径验证 |
| `write_file` | 写入文件 | 自动创建父目录 |
| `edit_file` | 精确替换文本 | 唯一性检查 |
| `list_dir` | 列出目录 | 类型标记 |
| `exec` | 执行 Shell | 危险命令拦截、超时、路径限制 |
| `web_search` | 网络搜索 | Brave Search API |
| `web_fetch` | 抓取网页 | URL 验证、内容截断 |
| `message` | 发送消息 | 跨渠道通信 |
| `spawn` | 启动子代理 | 后台任务 |

### 2. 消息总线模块 (`nanobot/bus/`)

```python
class MessageBus:
    """异步消息总线，解耦渠道与 Agent"""
    
    def __init__(self):
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()
        self._outbound_subscribers: dict[str, list[Callable]] = {}
    
    async def publish_inbound(self, msg: InboundMessage):
        """渠道发布入站消息"""
        await self.inbound.put(msg)
    
    async def consume_inbound(self) -> InboundMessage:
        """Agent 消费入站消息"""
        return await self.inbound.get()
    
    async def publish_outbound(self, msg: OutboundMessage):
        """Agent 发布出站消息"""
        await self.outbound.put(msg)
    
    def subscribe_outbound(self, channel: str, callback: Callable):
        """渠道订阅出站消息"""
        self._outbound_subscribers[channel].append(callback)
```

**设计优势**：
- **异步队列**：非阻塞消息传递
- **发布订阅**：多渠道可同时监听
- **类型安全**：InboundMessage / OutboundMessage 明确区分方向

### 3. 渠道管理模块 (`nanobot/channels/`)

```python
class BaseChannel(ABC):
    """渠道抽象基类"""
    
    name: str
    
    @abstractmethod
    async def start(self) -> None: ...   # 启动监听
    
    @abstractmethod
    async def stop(self) -> None: ...    # 停止清理
    
    @abstractmethod
    async def send(self, msg: OutboundMessage) -> None: ...  # 发送消息
    
    def is_allowed(self, sender_id: str) -> bool:
        """白名单检查"""
        allow_list = getattr(self.config, "allow_from", [])
        return not allow_list or sender_id in allow_list
```

**渠道实现方式**：

| 渠道 | 实现方式 | 技术栈 |
|:---|:---|:---|
| Telegram | Native Python | python-telegram-bot |
| WhatsApp | Bridge (Node.js) | Baileys + WebSocket |

### 4. LLM 提供商模块 (`nanobot/providers/`)

```python
class LLMProvider(ABC):
    """LLM 提供商抽象基类"""
    
    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None
    ) -> LLMResponse: ...

class LiteLLMProvider(LLMProvider):
    """通过 LiteLLM 支持多提供商"""
    
    # 自动检测提供商类型
    # - OpenRouter: api_key 以 sk-or- 开头
    # - vLLM: 设置了 api_base
    # - 智谱: 模型名包含 glm/zhipu
```

**支持的提供商**：
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude)
- Google (Gemini)
- OpenRouter (聚合平台)
- 智谱 AI (GLM)
- Groq
- vLLM (本地部署)

### 5. 记忆与技能模块

#### 5.1 MemoryStore - 记忆存储

```
workspace/
└── memory/
    ├── MEMORY.md              # 长期记忆
    ├── 2026-02-05.md          # 今日笔记
    ├── 2026-02-04.md          # 昨日笔记
    └── ...
```

```python
class MemoryStore:
    def read_long_term(self) -> str: ...
    def write_long_term(self, content: str): ...
    def read_today(self) -> str: ...
    def append_today(self, content: str): ...
    def get_recent_memories(self, days: int = 7) -> str: ...
```

#### 5.2 SkillsLoader - 技能加载

```
workspace/skills/          # 用户自定义技能
nanobot/skills/            # 内置技能
└── {skill-name}/
    └── SKILL.md           # 技能说明文档
```

**技能元数据**（YAML Frontmatter）：
```yaml
---
description: "技能描述"
always: true  # 是否总是加载
metadata: '{"nanobot": {"requires": {"bins": ["cli"], "env": ["KEY"]}}}'
---
```

---

## 数据流分析

### 1. 入站消息流（用户 → Agent）

```
用户发送消息
    │
    ▼
┌─────────────────┐
│  Telegram API   │ ←── 渠道特定协议
│  / WhatsApp Web │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Channel        │ ←── 解析消息格式
│  (Python/Node)  │
└────────┬────────┘
         │
         ▼ InboundMessage
┌─────────────────┐
│  MessageBus     │ ←── 发布到入站队列
│  publish_inbound│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  AgentLoop      │ ←── 消费消息
│  consume_inbound│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  SessionManager │ ←── 获取/创建会话
│  get_or_create  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  ContextBuilder │ ←── 构建 LLM 上下文
│  build_messages │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  ReAct Loop     │ ←── LLM 调用 + 工具执行
│  (迭代直到完成)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  OutboundMessage│ ←── 生成响应
└─────────────────┘
```

### 2. 出站消息流（Agent → 用户）

```
Agent 生成响应
    │
    ▼ OutboundMessage
┌─────────────────┐
│  MessageBus     │ ←── 发布到出站队列
│  publish_outbound│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Channel        │ ←── 订阅并接收消息
│  (Callback)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Telegram API   │ ←── 发送给用户
│  / WhatsApp Web │
└─────────────────┘
```

### 3. 工具调用流

```
LLM 返回 tool_calls
    │
    ▼
┌─────────────────┐
│  ToolRegistry   │ ←── 查找工具
│  get(name)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Tool.execute() │ ←── 执行工具逻辑
│  (异步)         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  返回结果       │ ←── 添加到消息历史
│  add_tool_result│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  继续 ReAct     │ ←── 下一轮 LLM 调用
│  Loop           │
└─────────────────┘
```

---

## 扩展机制

### 1. 添加新工具

```python
# nanobot/agent/tools/my_tool.py
class MyTool(Tool):
    @property
    def name(self) -> str:
        return "my_tool"
    
    @property
    def description(self) -> str:
        return "工具功能描述"
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "arg1": {"type": "string", "description": "参数1"}
            },
            "required": ["arg1"]
        }
    
    async def execute(self, arg1: str) -> str:
        # 实现逻辑
        return f"结果: {arg1}"

# 在 AgentLoop._register_default_tools() 中注册
self.tools.register(MyTool())
```

### 2. 添加新渠道

```python
# nanobot/channels/my_channel.py
class MyChannel(BaseChannel):
    name = "my_channel"
    
    async def start(self) -> None:
        # 连接到平台 API
        self.client = MyPlatformClient()
        self.client.on_message = self._on_message
        await self.client.connect()
    
    async def send(self, msg: OutboundMessage) -> None:
        await self.client.send_message(
            chat_id=msg.chat_id,
            text=msg.content
        )
```

### 3. 添加新技能

创建 `workspace/skills/my-skill/SKILL.md`：

```markdown
---
description: "我的技能"
always: false
---

# My Skill

这个技能教 Agent 如何做某事...

## 使用示例

```python
# 示例代码
```
```

---

## 配置体系

### 配置层级

```
┌─────────────────────────────────────────┐
│  1. 代码默认值 (schema.py)               │
│     model = "anthropic/claude-opus-4-5" │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│  2. 环境变量 (NANOBOT_*)                │
│     NANOBOT_AGENTS__DEFAULTS__MODEL=xxx │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│  3. 配置文件 (nanobot.yaml)             │
│     agents:                             │
│       defaults:                         │
│         model: xxx                      │
└─────────────────────────────────────────┘
```

### 配置模式 (Pydantic)

```python
class Config(BaseSettings):
    """根配置"""
    agents: AgentsConfig
    channels: ChannelsConfig
    providers: ProvidersConfig
    gateway: GatewayConfig
    tools: ToolsConfig
    
    class Config:
        env_prefix = "NANOBOT_"
        env_nested_delimiter = "__"
```

---

## 部署架构

### 单进程模式

```
┌─────────────────────────────────────────┐
│           Python Process                │
│                                         │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐ │
│  │Telegram │  │ Agent   │  │  Cron   │ │
│  │Channel  │  │ Loop    │  │ Service │ │
│  └────┬────┘  └────┬────┘  └────┬────┘ │
│       └─────────────┴─────────────┘     │
│                     │                   │
│              ┌──────▼──────┐            │
│              │ MessageBus  │            │
│              └─────────────┘            │
└─────────────────────────────────────────┘
```

适用场景：个人使用、开发测试

### Bridge 模式

```
┌─────────────────┐      WebSocket      ┌─────────────────┐
│  Node.js Process│ ◄──────────────────► │ Python Process  │
│                 │                      │                 │
│  ┌───────────┐  │                      │  ┌───────────┐  │
│  │ WhatsApp  │  │                      │  │ Agent     │  │
│  │ (Baileys) │  │                      │  │ Loop      │  │
│  └───────────┘  │                      │  └───────────┘  │
└─────────────────┘                      └─────────────────┘
```

适用场景：WhatsApp 等需要 Node.js 库的平台

---

## 总结

nanobot 的架构设计遵循以下原则：

1. **单一职责**：每个模块只负责一个明确的职责
2. **依赖倒置**：通过抽象基类（ABC）定义接口，具体实现可替换
3. **事件驱动**：消息总线解耦各模块，支持异步处理
4. **渐进式加载**：技能、记忆按需加载，控制上下文大小
5. **安全第一**：工具执行有严格的安全检查（命令拦截、路径限制）

这种设计使得 nanobot 在保持代码简洁（~5,000 行）的同时，具备强大的扩展能力和生产级稳定性。

---

*文档生成时间：2026-02-05*  
*作者：苏不胖 🦊*
