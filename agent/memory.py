from pathlib import Path
from mybot.utils.helpers import ensure_dir, today_date

class MemoryStore:
    """
    MemoryStore 的 Docstring
    """
    def __init__(self, workspace: Path):
        self.workspace = workspace 
        self.memory_dir = ensure_dir(workspace / "memory")
        self.memory_file = self.memory_dir / "MEMORY.md"

    def get_memory_context(self) -> str:
        """
        Get memory context for the agent.
        """
        parts = []

        long_term = self.read_long_term()
        if long_term:
            parts.append("## Long-term Memory\n" + long_term)

        today = self.read_today()
        if today:
            parts.append("## Today's Notes\n" + today)

        return "\n\n".join(parts) if parts else ""
    
    def read_long_term(self) -> str:
        """
        Read long-term memory (MEMORY.md)
        """
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""
    
    def read_today(self) -> str:
        """
        Read today's memory notes.
        """
        today_file = self.get_today_file()
        if today_file.exists():
            return today_file.read_text(encoding="utf-8")
        return ""
    
    def get_today_file(self) -> Path:
        """
        Get path to today's memory file.
        """
        return self.memory_dir / f"{today_date()}.md"