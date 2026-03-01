from typing import Any 
from mybot.agent.subagent import SubagentManager 
from mybot.agent.tools.base import Tool 

class SpawnTool(Tool):
    """
    为了执行后台任务，派生子 Agent。
    """
    def __init__(self, manager: "SubagentManager"):
        self._manager = manager 
        self._origin_channel = "cli"
        self._origin_chat_id = "direct"

    def set_context(self, channel: str, chat_id: str) -> None:
        self._origin_channel = channel 
        self._origin_chat_id = chat_id

    @property 
    def name(self) -> str:
        return "spawn"
    
    @property 
    def description(self) -> str:
        return (
            "Spawn a subagent to handle a task in the background. "
            "Use this for complex or time-consuming tasks that can run independently. "
            "The subagent will complete the task and report back when done."
        )
    
    @property 
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The task for the subagent to complete",
                },
                "label": {
                    "type": "string",
                    "description": "Optional short label for the task (for display)",
                },
            },
            "required": ["task"],
        }

    async def execute(self, task: str, label: str | None = None, **kwargs: Any) -> str:
        """
        派生 Agent, 执行指定的任务
        """
        return await self._manager.spawn(
            task=task,
            label=label,
            origin_channel=self._origin_channel,
            origin_chat_id=self._origin_chat_id,
        )