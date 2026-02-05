"""消息总线事件类型定义。

定义了在消息总线中流通的事件数据结构：
- InboundMessage: 从聊天渠道接收的消息
- OutboundMessage: 发送给聊天渠道的消息
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class InboundMessage:
    """入站消息：从聊天渠道接收到的消息。
    
    Attributes:
        channel: 渠道类型（telegram, discord, slack, whatsapp 等）
        sender_id: 发送者唯一标识
        chat_id: 聊天/频道唯一标识
        content: 消息文本内容
        timestamp: 消息时间戳
        media: 媒体文件 URL 列表（图片、音频等）
        metadata: 渠道特定数据（如 Telegram 的 update_id 等）
    """
    
    channel: str  # telegram, discord, slack, whatsapp
    sender_id: str  # User identifier
    chat_id: str  # Chat/channel identifier
    content: str  # Message text
    timestamp: datetime = field(default_factory=datetime.now)
    media: list[str] = field(default_factory=list)  # Media URLs
    metadata: dict[str, Any] = field(default_factory=dict)  # Channel-specific data
    
    @property
    def session_key(self) -> str:
        """会话唯一键：用于标识消息所属的会话。
        
        格式："{channel}:{chat_id}"
        例如："telegram:123456789"
        """
        return f"{self.channel}:{self.chat_id}"


@dataclass
class OutboundMessage:
    """出站消息：发送给聊天渠道的消息。
    
    Attributes:
        channel: 目标渠道类型
        chat_id: 目标聊天/频道标识
        content: 消息文本内容
        reply_to: 回复目标的消息 ID（可选）
        media: 媒体文件 URL 列表
        metadata: 额外元数据
    """
    
    channel: str
    chat_id: str
    content: str
    reply_to: str | None = None
    media: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


