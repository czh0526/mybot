from typing import Any 
from mybot.agent.tools.base import Tool 

class ToolRegistry:
    """
    ToolRegistry 的 Docstring
    """
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """
        register 的 Docstring
        
        :param self: 说明
        :param tool: 说明
        :type tool: Tool
        """
        self._tools[tool.name] = tool 

    def unregister(self, name: str) -> None:
        """
        unregister 的 Docstring
        
        :param self: 说明
        :param name: 说明
        :type name: str
        """
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        """
        get 的 Docstring
        
        :param self: 说明
        :param name: 说明
        :type name: str
        :return: 说明
        :rtype: Tool | None
        """
        return self._tools.get(name)
    
    def has(self, name: str) -> bool:
        """
        has 的 Docstring
        
        :param self: 说明
        :param name: 说明
        :type name: str
        :return: 说明
        :rtype: bool
        """
        return name in self._tools
    
    def get_definitions(self) -> list[dict[str, Any]]:
        """
        get_definitions 的 Docstring
        
        :param self: 说明
        :return: 说明
        :rtype: list[dict[str, Any]]
        """
        return [tool.to_schema() for tool in self._tools.values()]
    
    async def execute(self, name: str, params: dict[str, Any]) -> str:
        """
        execute 的 Docstring
        
        :param self: 说明
        :param name: 说明
        :type name: str
        :param params: 说明
        :type params: dict[str, Any]
        :return: 说明
        :rtype: str
        """
        tool = self._tools.get(name)
        if not tool:
            return f"Error: Tool '{name}' not found"
        
        try:
            errors = tool.validate_params(params)
            if errors:
                return f"Error: Invalid parameters for tool '{name}': " + "; ".join(errors)
            return await tool.execute(**params)
        except Exception as e:
            return f"Error executing {name}: {str(e)}"