from abc import ABC, abstractmethod
from typing import Any
from loguru import logger
from mybot.bus.events import InboundMessage
from mybot.bus.queue import MessageBus


class BaseChannel(ABC):
    """
    BaseChannel 的 Docstring
    """

    name: str = "base"

    def __init__(self, config: Any, bus: MessageBus):
        self.config = config
        self.bus = bus
        self._running = False

    @abstractmethod
    async def start(self) -> None:
        """
        开始通道服务，监听消息
        """
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """
        停止通道服务，清理资源
        """
        pass

    @abstractmethod
    async def send(self, message: str) -> None:
        """
        向通道发送消息
        """
        pass

    def is_allowed(self, sender_id: str) -> bool:
        """
        判断发送者是否在允许的列表中
        """
        allow_list = getattr(self.config, "allow_from", [])
        
        if not allow_list:
            return True 
        
        sender_str = str(sender_id)
        if sender_str in allow_list:
            return True 
        if "|" in sender_str:
            for part in sender_str.split("|"):
                if part and part in allow_list:
                    return True
        return False

    async def _handle_message(
        self, 
        sender_id: str, 
        chat_id: str,
        content: str,
        media: list[str] | None = None, 
        metadata: dict[str, Any] | None = None
     ) -> None:
        """
        处理接收到的消息，发布到总线
        """

        if not self.is_allowed(sender_id):
            logger.warning(
                f"消息来自未授权的发送者 {sender_id}，已拒绝",
                f"将它们加入配置文件的 allow_from 列表以允许它们发送消息"
            )
            return 
        
        msg = InboundMessage(
            channel=self.name,
            sender_id=str(sender_id),
            chat_id=str(chat_id),
            content=content,
            media=media or [],
            metadata=metadata or {}
        )

        await self.bus.publish_inbound(msg)

