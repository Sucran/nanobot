"""消息总线模块。

用于解耦聊天渠道与代理核心之间的通信。
采用异步队列实现，渠道将消息推入入站队列，代理处理后推送到出站队列。
"""

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
