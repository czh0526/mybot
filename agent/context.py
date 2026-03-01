import mimetypes
import base64
import platform 
from pathlib import Path 
from typing import Any 
from mybot.agent.memory import MemoryStore 
from mybot.agent.skills import SkillsLoader 

class ContextBuilder:
    """
    ContextBuilder 的 Docstring
    """
    BOOTSTRAP_FILES = ["AGENT.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md"]

    def __init__(self, workspace: Path):
        self.workspace = workspace 
        self.memory = MemoryStore(workspace)
        self.skills = SkillsLoader(workspace)

    def build_system_prompt(
        self, 
        skill_names: list[str] | None = None 
    ) -> str:
        """
        Build the system prompt from bootstrap files, memory, and skills.
        """
        parts = [] 

        # Core Identity
        parts.append(self._get_identity())

        # Bootstrap 
        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            parts.append(bootstrap)

        # Memory 
        memory = self.memory.get_memory_context()
        if memory:
            parts.append(f"# Memory\n\n{memory}")
        
        # Skills - progressive loading 
        
        return "\n\n---\n\n".join(parts)

        
    def _get_identity(self) -> str:
        """
        Get the core identity section.
        """
        from datetime import datetime 
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        workspace_path = str(self.workspace.expanduser().resolve())
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"

        return f"""# mybot 
你是mybot, 一个非常有用的AI助理. 你可以使用下面的工具:
- Read, write, and edit files
- Execute shell commands
- Search the web and fetch web pages
- Send messages to users on chat channels
- Spawn subagents for complex background tasks

## Current Time 
{now}

## Runtime 
{runtime}

## Workspace 
你的工作目录在 {workspace_path}
- Memory files: {workspace_path}/memory/MEMORY.md
- Daily notes: {workspace_path}/memory/YYYY-MM-DD.md
- Custom skills: {workspace_path}/skills/{{skill-name}}/SKILL.md

重要提示： 在回答直接问题或进行对话时，请直接以文本形式回复。 仅在需要向特定的聊天频道
（如 WhatsApp）发送消息时，才使用 'message' 工具。 对于普通对话，只需使用文本回复——不要调用消息工具。

始终保持乐于助人、准确且简练。在使用工具时，请解释你正在执行的操作。 当需要记录（记住）某些内容时，
请将其写入 {workspace_path}/memory/MEMORY.md。

"""

    def _load_bootstrap_files(self) -> str:
        """
        Load all bootstrap files from workspace.
        """
        parts = []

        for filename in self.BOOTSTRAP_FILES:
            file_path = self.workspace / filename 
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                parts.append(f"## {filename}\n\n{content}")

        return "\n\n".join(parts) if parts else ""

    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str, 
        skill_names: list[str] | None = None,
        media: list[str] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Build the complete message list for an LLM call.
        """
        messages = [] 

        # System prompt
        system_prompt = self.build_system_prompt(skill_names)
        if channel and chat_id:
            system_prompt += f"\n\n## Current Session\nChannel: {channel}\nChat ID: {chat_id}"
        messages.append({"role": "system", "content": system_prompt})

        # History
        messages.extend(history)

        user_content = self._build_user_content(current_message, media)
        messages.append({"role": "user", "content": user_content})

        return messages 
    
    def _build_user_content(self, text: str, media: list[str] | None) -> str | list[dict[str, Any]]:
        """
        Build user message content with optional base64-encoded images.
        """
        if not media:
            return text
        
        images = []
        for path in media:
            p = Path(path)
            mime, _ = mimetypes.guess_type(path)
            if not p.is_file() or not mime or not mime.startswith("image/"):
                continue 
            b64 = base64.b64encode(p.read_bytes()).decode()
            images.append({
                "type": "image_url", 
                "image_url": {
                    "url": f"data:{mime};base64,{b64}"
                }
            })

        if not images:
            return text 
        return images + [{"type": "text", "text": text}]
        

    def add_assistant_message(
        self,
        messages: list[dict[str, Any]],
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
        reasoning_content: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Add an assistant message to the message list.
        """
        msg: dict[str, Any] = {
            "role": "assistant",
            "content": content or "",
        }

        if tool_calls:
            msg["tool_calls"] = tool_calls 

        if reasoning_content:
            msg["reasoning_content"] = reasoning_content 
        
        messages.append(msg)
        return messages 

    def add_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_call_id: str, 
        tool_name: str,
        result: str 
    ) -> list[dict[str, Any]]:
        """
        Add a tool result to the message list.
        """
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result 
        })
        return messages 