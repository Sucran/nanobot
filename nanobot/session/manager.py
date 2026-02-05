"""会话管理模块。

管理 Agent 的对话会话，支持持久化和缓存。

会话存储：
- 格式：JSONL（每行一个 JSON 对象）
- 位置：~/.nanobot/sessions/{safe_key}.jsonl
- 结构：metadata 行 + message 行列表

会话键（key）格式：
- 通常为 "channel:chat_id"，如 "telegram:123456789"
- 用于唯一标识一个对话会话

使用示例：
    manager = SessionManager(workspace)
    
    # 获取或创建会话
    session = manager.get_or_create("telegram:123456789")
    
    # 添加消息
    session.add_message("user", "你好")
    session.add_message("assistant", "你好！有什么可以帮你的？")
    
    # 获取历史（用于 LLM 上下文）
    history = session.get_history(max_messages=50)
    
    # 保存会话
    manager.save(session)
"""

import json
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger

from nanobot.utils.helpers import ensure_dir, safe_filename


@dataclass
class Session:
    """对话会话。

    存储与单个用户的完整对话历史，支持持久化到 JSONL 文件。

    Attributes:
        key: 会话唯一标识（格式：channel:chat_id）
        messages: 消息列表，每条消息包含 role、content、timestamp 等
        created_at: 创建时间
        updated_at: 最后更新时间
        metadata: 额外元数据字典
    """

    key: str  # 会话键，如 "telegram:123456789"
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        """添加消息到会话。

        Args:
            role: 消息角色（"user", "assistant", "system", "tool"）
            content: 消息内容
            **kwargs: 额外字段（如 tool_calls、tool_call_id 等）
        """
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        self.messages.append(msg)
        self.updated_at = datetime.now()
    
    def get_history(self, max_messages: int = 50) -> list[dict[str, Any]]:
        """获取消息历史（用于 LLM 上下文）。

        只返回最近的 N 条消息，并简化为 LLM 所需的格式。

        Args:
            max_messages: 最大返回消息数，默认 50

        Returns:
            消息列表，格式为 [{"role": str, "content": str}, ...]
        """
        # 获取最近的消息
        recent = self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages
        
        # 转换为 LLM 格式（只保留 role 和 content）
        return [{"role": m["role"], "content": m["content"]} for m in recent]
    
    def clear(self) -> None:
        """清空会话中的所有消息。"""
        self.messages = []
        self.updated_at = datetime.now()


class SessionManager:
    """会话管理器。

    管理所有会话的生命周期：
    - 创建/获取会话
    - 加载/保存会话（持久化）
    - 缓存会话（内存中）
    - 删除会话
    - 列出现有会话

    会话存储位置：~/.nanobot/sessions/
    """

    def __init__(self, workspace: Path):
        """初始化会话管理器。

        Args:
            workspace: 工作区目录路径（用于确定会话存储位置）
        """
        self.workspace = workspace
        # 会话存储目录
        self.sessions_dir = ensure_dir(Path.home() / ".nanobot" / "sessions")
        # 会话缓存（内存中）
        self._cache: dict[str, Session] = {}
    
    def _get_session_path(self, key: str) -> Path:
        """获取会话文件路径。

        将 key 转换为安全的文件名。

        Args:
            key: 会话键

        Returns:
            会话文件的 Path 对象
        """
        safe_key = safe_filename(key.replace(":", "_"))
        return self.sessions_dir / f"{safe_key}.jsonl"
    
    def get_or_create(self, key: str) -> Session:
        """获取现有会话或创建新会话。

        查找顺序：
        1. 内存缓存
        2. 磁盘文件
        3. 创建新会话

        Args:
            key: 会话键（如 "telegram:123456789"）

        Returns:
            会话对象
        """
        # 检查缓存
        if key in self._cache:
            return self._cache[key]
        
        # 尝试从磁盘加载
        session = self._load(key)
        if session is None:
            session = Session(key=key)
        
        # 放入缓存
        self._cache[key] = session
        return session
    
    def _load(self, key: str) -> Session | None:
        """从磁盘加载会话。

        JSONL 文件格式：
        ```
        {"_type": "metadata", "created_at": "...", "metadata": {...}}
        {"role": "user", "content": "...", "timestamp": "..."}
        {"role": "assistant", "content": "...", "timestamp": "..."}
        ```

        Args:
            key: 会话键

        Returns:
            会话对象，如果文件不存在或读取失败则返回 None
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
                    
                    # 元数据行
                    if data.get("_type") == "metadata":
                        metadata = data.get("metadata", {})
                        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
                    else:
                        # 消息行
                        messages.append(data)
            
            return Session(
                key=key,
                messages=messages,
                created_at=created_at or datetime.now(),
                metadata=metadata
            )
        except Exception as e:
            logger.warning(f"Failed to load session {key}: {e}")
            return None
    
    def save(self, session: Session) -> None:
        """保存会话到磁盘。

        Args:
            session: 要保存的会话对象
        """
        path = self._get_session_path(session.key)
        
        with open(path, "w") as f:
            # 写入元数据行
            metadata_line = {
                "_type": "metadata",
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "metadata": session.metadata
            }
            f.write(json.dumps(metadata_line) + "\n")
            
            # 写入消息行
            for msg in session.messages:
                f.write(json.dumps(msg) + "\n")
        
        # 更新缓存
        self._cache[session.key] = session
    
    def delete(self, key: str) -> bool:
        """删除会话。

        Args:
            key: 会话键

        Returns:
            True 如果删除成功，False 如果会话不存在
        """
        # 从缓存移除
        self._cache.pop(key, None)
        
        # 删除文件
        path = self._get_session_path(key)
        if path.exists():
            path.unlink()
            return True
        return False
    
    def list_sessions(self) -> list[dict[str, Any]]:
        """列出所有会话。

        Returns:
            会话信息列表，每个元素包含 key、created_at、updated_at、path
        """
        sessions = []
        
        for path in self.sessions_dir.glob("*.jsonl"):
            try:
                # 只读取元数据行
                with open(path) as f:
                    first_line = f.readline().strip()
                    if first_line:
                        data = json.loads(first_line)
                        if data.get("_type") == "metadata":
                            sessions.append({
                                "key": path.stem.replace("_", ":"),
                                "created_at": data.get("created_at"),
                                "updated_at": data.get("updated_at"),
                                "path": str(path)
                            })
            except Exception:
                continue
        
        # 按更新时间倒序排列
        return sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True)
