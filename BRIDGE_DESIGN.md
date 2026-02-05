# nanobot Bridge 设计说明文档

## 目录

1. [架构概述](#架构概述)
2. [Bridge 设计模式](#bridge-设计模式)
3. [WhatsApp Bridge 实现](#whatsapp-bridge-实现)
4. [Telegram Channel 实现](#telegram-channel-实现)
5. [两种方案的对比](#两种方案的对比)
6. [扩展指南](#扩展指南)

---

## 架构概述

nanobot 采用**多语言混合架构**：

```
┌─────────────────────────────────────────────────────────────┐
│                      用户消息来源                            │
│         WhatsApp        Telegram        其他渠道            │
└──────────┬────────────────┬────────────────┬────────────────┘
           │                │                │
           ▼                ▼                ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  WhatsApp Bridge │  │ Telegram Channel │  │   其他 Bridge    │
│   (Node.js)      │  │    (Python)      │  │                  │
└──────────┬───────┘  └──────────┬───────┘  └──────────┬───────┘
           │                     │                     │
           └─────────────────────┼─────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │     MessageBus         │
                    │    (Python 异步队列)    │
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │      AgentLoop         │
                    │    (Python 核心逻辑)    │
                    └────────────────────────┘
```

**设计哲学**：
- **核心逻辑统一**：AgentLoop、消息总线、工具系统全部用 Python 实现
- **渠道适配灵活**：根据渠道特性选择最佳技术栈
- **统一消息格式**：所有渠道通过 `InboundMessage` / `OutboundMessage` 与核心通信

---

## Bridge 设计模式

### 1. 抽象基类设计（Python Channel）

```python
class BaseChannel(ABC):
    """聊天渠道抽象基类"""
    
    name: str = "base"
    
    def __init__(self, config: Any, bus: MessageBus):
        self.config = config      # 渠道配置
        self.bus = bus            # 消息总线
        self._running = False
    
    @abstractmethod
    async def start(self) -> None:
        """启动渠道，开始监听消息"""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """停止渠道，清理资源"""
        pass
    
    @abstractmethod
    async def send(self, msg: OutboundMessage) -> None:
        """发送消息到渠道"""
        pass
```

**核心方法**：
- `start()` / `stop()`: 生命周期管理
- `send()`: 出站消息发送
- `_handle_message()`: 入站消息处理（封装为 InboundMessage 发送到总线）
- `is_allowed()`: 访问控制（白名单机制）

### 2. Bridge 设计（Node.js）

```typescript
// 独立的 Node.js 进程，通过 WebSocket 与 Python 通信
class BridgeServer {
    private wss: WebSocketServer;      // WebSocket 服务器
    private wa: WhatsAppClient;        // WhatsApp 客户端
    private clients: Set<WebSocket>;   // 连接的 Python 客户端
    
    async start(): Promise<void> {
        // 1. 启动 WebSocket 服务器（监听 Python 连接）
        // 2. 初始化 WhatsApp 客户端
        // 3. 转发消息：WhatsApp ↔ Python
    }
}
```

**通信协议**：

```typescript
// Python → Bridge (发送消息)
interface SendCommand {
    type: 'send';
    to: string;      // 目标手机号/群组ID
    text: string;    // 消息内容
}

// Bridge → Python (收到消息)
interface InboundMessage {
    type: 'message';
    id: string;
    sender: string;
    content: string;
    timestamp: number;
    isGroup: boolean;
}

// Bridge → Python (状态通知)
interface StatusMessage {
    type: 'status' | 'qr' | 'error';
    ...
}
```

---

## WhatsApp Bridge 实现

### 技术选型

| 组件 | 技术 | 理由 |
|:---|:---|:---|
| 运行时 | Node.js 20+ | Baileys 库依赖 |
| WhatsApp 库 | Baileys | 开源、无官方 API 限制、功能完整 |
| 通信协议 | WebSocket | 双向实时通信、跨语言支持 |
| QR 码 | qrcode-terminal | 终端扫码登录 |

### 架构图

```
┌────────────────────────────────────────────────────────────┐
│                    WhatsApp Bridge                          │
│                     (Node.js 进程)                          │
│                                                             │
│  ┌─────────────────┐        ┌──────────────────────────┐   │
│  │  WhatsAppClient │        │      BridgeServer        │   │
│  │    (Baileys)    │◄──────►│     (WebSocket)          │   │
│  │                 │        │                          │   │
│  │ - connect()     │        │ - port: 3001             │   │
│  │ - sendMessage() │        │ - handleCommand()        │   │
│  │ - onMessage     │        │ - broadcast()            │   │
│  │ - onQR          │        │                          │   │
│  └─────────────────┘        └───────────┬──────────────┘   │
│                                         │                  │
└─────────────────────────────────────────┼──────────────────┘
                                          │ WebSocket
                                          ▼
                              ┌───────────────────────┐
                              │   Python nanobot      │
                              │   (WhatsAppChannel)   │
                              └───────────────────────┘
```

### 核心实现

#### 1. WhatsAppClient (Baileys 封装)

```typescript
export class WhatsAppClient {
    private sock: any;  // Baileys socket 实例
    
    async connect(): Promise<void> {
        // 1. 加载认证状态（实现持久登录）
        const { state, saveCreds } = await useMultiFileAuthState(this.authDir);
        
        // 2. 创建 socket
        this.sock = makeWASocket({
            auth: { creds: state.creds, keys: ... },
            version,           // WhatsApp Web 版本
            printQRInTerminal: false,  // 自定义 QR 处理
            browser: ['nanobot', 'cli', VERSION],
            syncFullHistory: false,     // 不同步历史
        });
        
        // 3. 事件监听
        this.sock.ev.on('connection.update', (update) => {
            // 处理连接状态：qr（扫码）、open（已连接）、close（断开）
        });
        
        this.sock.ev.on('messages.upsert', ({ messages }) => {
            // 处理收到的消息
        });
        
        this.sock.ev.on('creds.update', saveCreds);  // 自动保存认证
    }
}
```

**关键特性**：
- **持久登录**：认证信息保存到 `~/.nanobot/whatsapp-auth/`
- **自动重连**：非主动登出时自动重连（5秒延迟）
- **消息提取**：支持文本、图片、视频、语音、文档

#### 2. BridgeServer (WebSocket 服务器)

```typescript
export class BridgeServer {
    async start(): Promise<void> {
        // 创建 WebSocket 服务器，Python 客户端连接
        this.wss = new WebSocketServer({ port: this.port });
        
        // 初始化 WhatsApp
        this.wa = new WhatsAppClient({
            onMessage: (msg) => this.broadcast({ type: 'message', ...msg }),
            onQR: (qr) => this.broadcast({ type: 'qr', qr }),
            onStatus: (status) => this.broadcast({ type: 'status', status }),
        });
        
        // 处理 Python 客户端连接
        this.wss.on('connection', (ws) => {
            ws.on('message', async (data) => {
                const cmd = JSON.parse(data.toString());
                await this.handleCommand(cmd);  // 转发到 WhatsApp
            });
        });
    }
    
    private async handleCommand(cmd: SendCommand): Promise<void> {
        if (cmd.type === 'send') {
            await this.wa.sendMessage(cmd.to, cmd.text);
        }
    }
}
```

#### 3. Python 端集成

```python
# nanobot/channels/whatsapp.py
class WhatsAppChannel(BaseChannel):
    """通过 Bridge 连接 WhatsApp"""
    
    async def start(self) -> None:
        # 1. 启动 Bridge 进程（Node.js）
        self._bridge_process = await asyncio.create_subprocess_exec(
            "node", "bridge/dist/index.js",
            env={"BRIDGE_PORT": "3001", ...}
        )
        
        # 2. 连接 WebSocket
        self._ws = await websockets.connect("ws://localhost:3001")
        
        # 3. 监听消息
        async for message in self._ws:
            data = json.loads(message)
            if data["type"] == "message":
                await self._handle_message(...)
            elif data["type"] == "qr":
                # 显示二维码给用户
                print(f"请扫码: {data['qr']}")
    
    async def send(self, msg: OutboundMessage) -> None:
        # 发送消息到 Bridge
        await self._ws.send(json.dumps({
            "type": "send",
            "to": msg.chat_id,
            "text": msg.content
        }))
```

### 启动流程

```
1. 用户启动 nanobot
   │
   ▼
2. nanobot 启动 WhatsAppChannel
   │
   ▼
3. WhatsAppChannel 启动 Bridge 子进程（Node.js）
   │
   ▼
4. Bridge 启动 WebSocket 服务器（端口 3001）
   │
   ▼
5. Bridge 初始化 Baileys，显示 QR 码
   │
   ▼
6. 用户扫码，WhatsApp Web 连接成功
   │
   ▼
7. Python ←WebSocket→ Node.js 连接建立，开始转发消息
```

---

## Telegram Channel 实现

### 技术选型

| 组件 | 技术 | 理由 |
|:---|:---|:---|
| 运行时 | Python asyncio | 与 nanobot 核心统一 |
| Telegram 库 | python-telegram-bot | 官方推荐、功能完整、文档丰富 |
| 通信方式 | Long Polling | 无需公网 IP、简单可靠 |
| 消息格式 | HTML | 支持格式化、比 Markdown 安全 |

### 架构图

```
┌────────────────────────────────────────────────────────────┐
│                    Telegram Channel                         │
│                     (Python 原生)                           │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              TelegramChannel (BaseChannel)            │  │
│  │                                                      │  │
│  │  ┌──────────────┐      ┌────────────────────────┐   │  │
│  │  │  Application │◄────►│  python-telegram-bot   │   │  │
│  │  │  (Polling)   │      │    (Long Polling)      │   │  │
│  │  └──────────────┘      └───────────┬────────────┘   │  │
│  │                                    │                │  │
│  │  消息处理器:                       │ Telegram API   │  │
│  │  - _on_message()  ────────────────┘                │  │
│  │  - _on_start()                                      │  │
│  │                                                    │  │
│  │  发送方法:                                          │  │
│  │  - send() → bot.send_message()                      │  │
│  │                                                    │  │
│  └──────────────────────┬─────────────────────────────┘  │
│                         │                                 │
└─────────────────────────┼─────────────────────────────────┘
                          │ InboundMessage/OutboundMessage
                          ▼
              ┌───────────────────────┐
              │      MessageBus       │
              └───────────────────────┘
```

### 核心实现

#### 1. TelegramChannel 类

```python
class TelegramChannel(BaseChannel):
    """Telegram 渠道实现（Long Polling 模式）"""
    
    name = "telegram"
    
    def __init__(self, config: TelegramConfig, bus: MessageBus, ...):
        super().__init__(config, bus)
        self._app: Application | None = None  # PTB Application
        self._chat_ids: dict[str, int] = {}    # 用户 ID 映射
    
    async def start(self) -> None:
        """启动 Telegram Bot（Long Polling）"""
        # 1. 创建 Application
        self._app = Application.builder().token(self.config.token).build()
        
        # 2. 添加消息处理器
        self._app.add_handler(
            MessageHandler(
                filters.TEXT | filters.PHOTO | filters.VOICE | ...,
                self._on_message
            )
        )
        
        # 3. 启动 Polling
        await self._app.updater.start_polling(
            drop_pending_updates=True  # 忽略启动前的旧消息
        )
    
    async def send(self, msg: OutboundMessage) -> None:
        """发送消息到 Telegram"""
        # Markdown → Telegram HTML 转换
        html_content = _markdown_to_telegram_html(msg.content)
        
        await self._app.bot.send_message(
            chat_id=int(msg.chat_id),
            text=html_content,
            parse_mode="HTML"
        )
```

#### 2. Markdown 转 Telegram HTML

Telegram 的 HTML 格式与标准 Markdown 有差异，需要转换：

```python
def _markdown_to_telegram_html(text: str) -> str:
    """将 Markdown 转换为 Telegram 安全的 HTML"""
    
    # 1. 保护代码块（防止被其他规则处理）
    code_blocks = []
    text = re.sub(r'```[\w]*\n?([\s\S]*?)```', 
                  lambda m: save_code_block(m), text)
    
    # 2. 转换格式
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)      # **粗体** → <b>
    text = re.sub(r'_(.+?)_', r'<i>\1</i>', text)             # _斜体_ → <i>
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)',                 # [链接](url) → <a>
                  r'<a href="\2">\1</a>', text)
    
    # 3. 恢复代码块
    text = text.replace(f"\x00CB{i}\x00", 
                        f"<pre><code>{code}</code></pre>")
    
    return text
```

**转换规则**：
| Markdown | Telegram HTML |
|:---|:---|
| `**text**` | `<b>text</b>` |
| `_text_` | `<i>text</i>` |
| `[link](url)` | `<a href="url">link</a>` |
| `` `code` `` | `<code>code</code>` |
| ` ```code``` ` | `<pre><code>code</code></pre>` |

#### 3. 媒体文件处理

```python
async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理收到的消息（包括媒体）"""
    
    # 1. 提取文本内容
    content_parts = []
    if message.text:
        content_parts.append(message.text)
    if message.caption:
        content_parts.append(message.caption)
    
    # 2. 处理媒体文件
    media_paths = []
    
    if message.photo:
        # 下载图片
        file = await self._app.bot.get_file(message.photo[-1].file_id)
        file_path = media_dir / f"{file_id}.jpg"
        await file.download_to_drive(str(file_path))
        media_paths.append(str(file_path))
        
    elif message.voice or message.audio:
        # 下载语音 → 转录
        file_path = ...
        transcription = await transcriber.transcribe(file_path)
        content_parts.append(f"[transcription: {transcription}]")
    
    # 3. 发送到消息总线
    await self._handle_message(
        sender_id=str(user.id),
        chat_id=str(message.chat_id),
        content="\n".join(content_parts),
        media=media_paths,
        metadata={...}
    )
```

---

## 两种方案的对比

| 维度 | WhatsApp (Bridge) | Telegram (Native) |
|:---|:---|:---|
| **技术栈** | Node.js + TypeScript | Python + asyncio |
| **运行方式** | 独立进程（子进程） | 同进程（协程） |
| **通信方式** | WebSocket | 直接方法调用 |
| **库依赖** | Baileys (第三方) | python-telegram-bot (官方) |
| **认证方式** | QR 码扫码 | Bot Token |
| **部署复杂度** | 高（需 Node.js 环境） | 低（纯 Python） |
| **启动速度** | 慢（需启动子进程） | 快（同进程） |
| **适用场景** | 需绕过官方 API 限制 | 官方 API 充足 |

### 设计决策分析

**为什么选择 Bridge 模式实现 WhatsApp？**

1. **技术限制**：
   - WhatsApp 官方 Business API 需要 Meta 商业账号
   - 第三方 Python 库（如 yowsup）功能有限、维护不活跃
   - Baileys（Node.js）是目前最成熟的开源方案

2. **架构优势**：
   - Bridge 进程崩溃不影响 Python 核心
   - 可以独立升级 WhatsApp 库
   - WebSocket 协议便于多语言集成

**为什么选择 Native 模式实现 Telegram？**

1. **生态成熟**：
   - python-telegram-bot 功能完整、文档丰富
   - Long Polling 简单可靠，无需 Webhook

2. **性能考虑**：
   - 同进程通信开销更低
   - 避免子进程管理复杂度

---

## 扩展指南

### 添加新的 Bridge 渠道（如 Discord）

```typescript
// bridge/src/discord.ts
export class DiscordClient {
    // 1. 实现 Discord bot 连接（使用 discord.js）
    // 2. 提供 onMessage、sendMessage 接口
}

// bridge/src/server.ts - 扩展支持多渠道
class BridgeServer {
    private discord: DiscordClient | null = null;
    
    async startDiscord(): Promise<void> {
        this.discord = new DiscordClient({
            onMessage: (msg) => this.broadcast({ 
                type: 'message', 
                channel: 'discord',
                ...msg 
            })
        });
    }
}
```

### 添加新的 Native 渠道（如 Slack）

```python
# nanobot/channels/slack.py
class SlackChannel(BaseChannel):
    name = "slack"
    
    async def start(self) -> None:
        # 使用 slack-sdk 实现
        self.client = SocketModeClient(...)
        self.client.socket_mode_request_listeners.append(self._on_message)
    
    async def send(self, msg: OutboundMessage) -> None:
        await self.client.chat_postMessage(
            channel=msg.chat_id,
            text=msg.content
        )
```

### 选择标准

| 情况 | 推荐方案 |
|:---|:---|
| 有成熟的 Python SDK | Native（如 Telegram） |
| 只有 Node.js SDK | Bridge（如 WhatsApp） |
| 官方 API 严格限制 | Bridge（使用逆向库） |
| 需要复杂媒体处理 | Native（减少跨进程传输） |

---

## 总结

nanobot 的 Bridge 架构提供了**灵活的渠道扩展能力**：

1. **统一接口**：所有渠道通过 `BaseChannel` 统一接入
2. **技术无关**：根据 SDK 生态选择 Python 或 Node.js 实现
3. **消息标准化**：统一的 `InboundMessage` / `OutboundMessage` 格式
4. **通信解耦**：WebSocket Bridge 模式实现多语言协作

这种设计让 nanobot 可以快速适配任何聊天平台，而不受限于单一技术栈。

---

*文档生成时间：2026-02-05*  
*作者：苏不胖 🦊*
