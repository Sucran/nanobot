"""异步消息队列模块。

提供解耦的渠道-代理通信机制：
- 入站队列：渠道推送消息到代理
- 出站队列：代理响应推送到渠道
- 发布/订阅模式：支持多渠道订阅出站消息
"""

import asyncio
from typing import Callable, Awaitable

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage


class MessageBus:
    """异步消息总线。
    
    解耦聊天渠道与代理核心之间的通信：
    - 渠道将消息推入入站队列
    - 代理处理消息并将响应推入出站队列
    - 支持渠道订阅出站消息
    
    Attributes:
        inbound: 入站消息队列（渠道 -> 代理）
        outbound: 出站消息队列（代理 -> 渠道）
    """
    
    def __init__(self):
        # 入站队列：存储从各渠道接收的消息
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        # 出站队列：存储要发送给各渠道的消息
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()
        # 出站消息订阅者：channel -> [callback列表]
        self._outbound_subscribers: dict[str, list[Callable[[OutboundMessage], Awaitable[None]]]] = {}
        self._running = False  # 调度器运行状态
    
    async def publish_inbound(self, msg: InboundMessage) -> None:
        """发布入站消息（从渠道到代理）。
        
        Args:
            msg: 入站消息对象
        """
        await self.inbound.put(msg)
    
    async def consume_inbound(self) -> InboundMessage:
        """消费下一个入站消息（阻塞直到可用）。
        
        Returns:
            下一个入站消息
            
        Raises:
            asyncio.CancelledError: 当队列被关闭时
        """
        return await self.inbound.get()
    
    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """发布出站消息（从代理到渠道）。
        
        Args:
            msg: 出站消息对象
        """
        await self.outbound.put(msg)
    
    async def consume_outbound(self) -> OutboundMessage:
        """消费下一个出站消息（阻塞直到可用）。
        
        Returns:
            下一个出站消息
        """
        return await self.outbound.get()
    
    def subscribe_outbound(
        self, 
        channel: str, 
        callback: Callable[[OutboundMessage], Awaitable[None]]
    ) -> None:
        """订阅特定渠道的出站消息。
        
        当有出站消息时，注册的回调函数会被调用。
        
        Args:
            channel: 渠道名称（如 'telegram', 'discord'）
            callback: 异步回调函数，接收 OutboundMessage
        """
        if channel not in self._outbound_subscribers:
            self._outbound_subscribers[channel] = []
        self._outbound_subscribers[channel].append(callback)
    
    async def dispatch_outbound(self) -> None:
        """调度出站消息到订阅的渠道。
        
        作为后台任务运行，持续检查出站队列并将消息分发给
        对应渠道的订阅者。
        
        工作流程：
        1. 从出站队列获取消息
        2. 根据消息的 channel 查找订阅者
        3. 并行调用所有订阅者的回调函数
        4. 记录分发错误但不中断调度
        """
        self._running = True
        while self._running:
            try:
                # 等待出站消息，超时1秒以便检查停止标志
                msg = await asyncio.wait_for(self.outbound.get(), timeout=1.0)
                # 获取该渠道的所有订阅者
                subscribers = self._outbound_subscribers.get(msg.channel, [])
                # 遍历调用每个订阅者的回调
                for callback in subscribers:
                    try:
                        await callback(msg)
                    except Exception as e:
                        logger.error(f"Error dispatching to {msg.channel}: {e}")
            except asyncio.TimeoutError:
                # 超时是正常的，继续循环检查停止标志
                continue
    
    def stop(self) -> None:
        """停止调度器循环。
        
        设置停止标志，dispatch_outbound 会在下一次超时后退出。
        """
        self._running = False
    
    @property
    def inbound_size(self) -> int:
        """获取待处理入站消息数量。
        
        Returns:
            入站队列中的消息数量
        """
        return self.inbound.qsize()
    
    @property
    def outbound_size(self) -> int:
        """获取待处理出站消息数量。
        
        Returns:
            出站队列中的消息数量
        """
        return self.outbound.qsize()
