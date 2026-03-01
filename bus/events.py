from dataclasses import dataclass, field 
from datetime import datetime 
from typing import Any 

@dataclass 
class InboundMessage:
    """表示从外部系统接收到的消息"""

    channel: str
    chat_id: str 
    content: str
    sender_id: str 
    timstamp: datetime = field(default_factory=datetime.now)
    media: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property 
    def session_key(self) -> str:
        """生成一个唯一的会话键，用于关联消息和智能体会话"""
        return f"{self.channel}:{self.chat_id}"
    
@dataclass
class OutboundMessage:
    """表示要发送到外部系统的消息"""

    channel: str 
    chat_id: str
    content: str
    reply_to: str | None = None 
    media: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
