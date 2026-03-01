import asyncio 
from loguru import logger
from typing import Callable, Awaitable 
from mybot.bus.events import InboundMessage, OutboundMessage

class MessageBus:
    """
    MessageBus 的 Docstring
    """
    def __init__(self):
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue() 
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()
        self._outbound_subscribers: dict[str, list[Callable[[OutboundMessage], Awaitable[None]]]] = {}
        self._running = False 

    async def publish_inbound(self, message: InboundMessage) -> None:
        """
        发布消息到Agent 
        """
        logger.info(f"插入 inbound 队列: {message.content}")
        await self.inbound.put(message)

    async def consume_inbound(self) -> InboundMessage:
        """
        从队列中获取消息(如果没有会持续等待)
        """
        
        msg = await self.inbound.get()
        logger.info(f"从 inbound 队列中获取: {msg.content}")
        return msg 

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """
        发布消息到渠道
        """
        return await self.outbound.put(msg)
        
    async def consume_outbound(self) -> OutboundMessage:
        """
        从队列中获取消息(如果没有会持续等待)
        """
        return await self.outbound.get()

    def subscribe_outbound(
            self, 
            channel: str, 
            callback: Callable[[OutboundMessage], Awaitable[None]]
    ) -> None:
        """
        订阅一个主题并注册回调函数
        """
        if channel not in self._outbound_subscribers:
            self._outbound_subscribers[channel] = []
        self._outbound_subscribers[channel].append(callback)

    async def dispatch_outbound(self) -> None:
        """
        分发消息到订阅者
        """
        self._running = True
        while self._running:
            try:
                msg = await asyncio.wait_for(self.outbound.get(), timeout=1.0)
                subscribers = self._outbound_subscribers.get(msg.channel, [])
                for callback in subscribers:
                    try:
                        await callback(msg)
                    except Exception as e:
                        logger.error(f"Error dispatching to {msg.channel}: {e}")

            except asyncio.TimeoutError:
                continue

    def stop(self) -> None:
        """
        停止消息总线的分发循环
        """
        self._running = False

    @property
    def inbound_size(self) -> int:
        """
        获取当前入站消息队列的大小
        """
        return self.inbound.qsize()
    
    @property 
    def outbound_size(self) -> int:
        """
        获取当前出站消息队列的大小
        """
        return self.outbound.qsize()