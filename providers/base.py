from abc import ABC, abstractmethod 
from dataclasses import dataclass, field
from typing import Any 

@dataclass 
class ToolCallRequest:
    """
    ToolCallRequest 的 Docstring
    """
    id: str
    name: str 
    arguments: dict[str, Any]

@dataclass 
class LLMResponse:
    """
    LLMResponse 的 Docstring
    """
    content: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    reasoning_content: str | None = None 

    @property
    def has_tool_calls(self) -> bool:
        """
        has_tool_calls 的 Docstring
        
        :param self: 说明
        :return: 说明
        :rtype: bool
        """
        return len(self.tool_calls) > 0 
    
class LLMProvider(ABC):
    """
    LLMProvider 的 Docstring
    """
    def __init__(self, api_key: str|None = None, api_base: str|None = None):
        self.api_key = api_key 
        self.api_base = api_base 

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        chat 的 Docstring
        
        :param self: 说明
        :param messages: 说明
        :type messages: list[dict[str, Any]]
        :param tools: 说明
        :type tools: list[dict[str, Any]] | None
        :param model: 说明
        :type model: str | None
        :param max_tokens: 说明
        :type max_tokens: int
        :param temperature: 说明
        :type temperature: float
        :return: 说明
        :rtype: LLMResponse
        """
        pass  

    @abstractmethod 
    def get_default_model(self) -> str:
        """
        get_default_model 的 Docstring
        
        :param self: 说明
        :return: 说明
        :rtype: str
        """
        pass 