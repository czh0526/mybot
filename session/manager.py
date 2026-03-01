import json 
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime 
from typing import Any
from loguru import logger 
from mybot.utils.helpers import ensure_dir, safe_filename

@dataclass
class Session: 
    """会话类，存储会话相关的数据"""
    
    key: str 
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        """向会话中添加一条消息"""
        self.messages.append({
            "role": role,
            "content": content,
            **kwargs
        })
        self.updated_at = datetime.now()

    def get_history(self, max_messages: int = 50) -> list[dict[str, Any]]:
        """ 
        获取会话历史消息，默认返回最近的50条
        """

        recent = self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages

        return [{"role": m["role"], "content": m["content"]} for m in recent]

    def clear(self) -> None:
        """清除会话历史消息"""
        self.messages = []
        self.updated_at = datetime.now()


class SessionManager:

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.sessions_dir = ensure_dir(Path.home()/".mybot"/ "sessions")  
        self._cache: dict[str, Session] = {} # 存储会话数据的字典

    def _get_session_path(self, key: str) -> Path:
        """
        获取会话数据文件的路径
        """
        safe_key = safe_filename(key.replace(":", "_"))
        return self.sessions_dir / f"{safe_key}.jsonl"

    def get_or_create(self, key: str) -> Session:
        """
        获取一个已经存在的回话、或者创建一个新的会话
        """
        if key in self._cache:
            return self._cache[key]
        
        session= self._load(key)
        if session is None:
            session = Session(key=key) 

        self._cache[key] = session 
        return session 
    
    def _load(self, key: str) -> Session | None:
        """
        从文件加载会话数据
        """
        path = self._get_session_path(key)
        if not path.exists():
            return None 
        try:
            messages = []
            metadata = {}
            created_at = None 

            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    data = json.loads(line)

                    if data.get("_type") == "metadata":
                        metadata = data.get("data", {})
                        created_at = datetime.fromisoformat(data["created_at"]) if metadata.get("created_at") else None
                    else:
                        messages.append(data)

            return Session(
                key=key, 
                messages=messages,
                created_at=created_at or datetime.now(),
                metadata=metadata
            )
        except Exception as e:
            logger.warning(f"加载会话数据失败: {key}: {e}")
            return None 

    def save(self, session: Session) -> None:
        """
        将会话数据保存到文件
        """
        path = self._get_session_path(session.key)
        try:
            with open(path, "w") as f:
                # 先写入元数据
                metadata_entry = {
                    "_type": "metadata",
                    "created_at": session.created_at.isoformat(),
                    "data": session.metadata
                }
                f.write(json.dumps(metadata_entry) + "\n")

                # 再写入消息数据
                for message in session.messages:
                    f.write(json.dumps(message) + "\n")
        except Exception as e:
            logger.error(f"保存会话数据失败: {session.key}: {e}")

    def save(self, session: Session) -> None:
        """
        将会话数据保存到文件
        """
        path = self._get_session_path(session.key)

        with open(path, "w") as f:
            # 先写入元数据
            metadata_line = {
                "_type": "metadata",
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "metadata": session.metadata
            }
            f.write(json.dumps(metadata_line) + "\n")

            # 再写入消息数据
            for msg in session.messages:
                f.write(json.dumps(msg) + "\n")

        self._cache[session.key] = session

    def delete(self, key: str) -> bool:
        """
        删除一个会话
        """
        self._cache.pop(key, None)

        path = self._get_session_path(key)
        if path.exists():
            path.unlink()
            return True 
        return False 

    def list_sessions(self) -> list[dict[str, Any]]:
        """
        列出所有会话
        """
        sessions = []
        for path in self.sessions_dir.glob("*.jsonl"):
            try:
                with open(path) as f:
                    first_line = f.readline().strip()
                    if  first_line:
                        data = json.loads(first_line)
                        if data.get("_type") == "metadata":
                            sessions.append({
                                "key": path.stem.replace("_", ":"),
                                "created_at": data.get("created_at"),
                                "updated_at": data.get("updated_at"),
                                "path": str(path)
                            })
            except Exception as e:
                continue 
            
        return sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True)