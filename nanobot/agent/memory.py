"""记忆系统模块。

提供持久的 Agent 记忆功能：
- MemoryStore: 记忆存储中心

记忆类型：
1. 每日笔记: memory/YYYY-MM-DD.md
   - 当天的临时笔记和记录
   - 自动按日期归档

2. 长期记忆: memory/MEMORY.md
   - 持久化的重要信息
   - 跨会话保留

使用场景：
- 记录用户偏好
- 保存对话上下文
- 存储学习到的信息
"""

from pathlib import Path
from datetime import datetime

from nanobot.utils.helpers import ensure_dir, today_date


class MemoryStore:
    """记忆存储中心。

    管理 Agent 的记忆，包括：
    - 每日笔记（短期记忆）
    - 长期记忆（持久化）

    文件结构：
    ```
    workspace/
    └── memory/
        ├── MEMORY.md           # 长期记忆
        ├── 2026-02-05.md       # 今天的笔记
        ├── 2026-02-04.md       # 昨天的笔记
        └── ...
    ```

    使用示例：
        store = MemoryStore(workspace)
        
        # 记录今天的笔记
        store.append_today("用户喜欢 Python")
        
        # 保存长期记忆
        store.write_long_term("用户邮箱: user@example.com")
        
        # 获取最近 7 天的记忆
        recent = store.get_recent_memories(days=7)
    """

    def __init__(self, workspace: Path):
        """初始化记忆存储。

        Args:
            workspace: 工作区目录路径
        """
        self.workspace = workspace
        # 确保 memory 目录存在
        self.memory_dir = ensure_dir(workspace / "memory")
        # 长期记忆文件路径
        self.memory_file = self.memory_dir / "MEMORY.md"
    
    def get_today_file(self) -> Path:
        """获取今天的记忆文件路径。

        Returns:
            今天的 markdown 文件路径（如 memory/2026-02-05.md）
        """
        return self.memory_dir / f"{today_date()}.md"
    
    def read_today(self) -> str:
        """读取今天的笔记。

        Returns:
            今天笔记的内容，如果不存在返回空字符串
        """
        today_file = self.get_today_file()
        if today_file.exists():
            return today_file.read_text(encoding="utf-8")
        return ""
    
    def append_today(self, content: str) -> None:
        """追加内容到今天的笔记。

        如果今天的文件不存在，会自动创建并添加日期标题。

        Args:
            content: 要追加的内容
        """
        today_file = self.get_today_file()
        
        if today_file.exists():
            # 追加到现有内容
            existing = today_file.read_text(encoding="utf-8")
            content = existing + "\n" + content
        else:
            # 新文件：添加日期标题
            header = f"# {today_date()}\n\n"
            content = header + content
        
        today_file.write_text(content, encoding="utf-8")
    
    def read_long_term(self) -> str:
        """读取长期记忆。

        Returns:
            MEMORY.md 的内容，如果不存在返回空字符串
        """
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""
    
    def write_long_term(self, content: str) -> None:
        """写入长期记忆。

        会完全覆盖 MEMORY.md 的内容。

        Args:
            content: 要写入的内容
        """
        self.memory_file.write_text(content, encoding="utf-8")
    
    def get_recent_memories(self, days: int = 7) -> str:
        """获取最近 N 天的记忆。

        从最近的一天开始往前回溯，收集所有存在的每日笔记。

        Args:
            days: 回溯天数，默认 7 天

        Returns:
            合并后的记忆内容，按时间倒序排列（最新的在前）
        """
        from datetime import timedelta
        
        memories = []
        today = datetime.now().date()
        
        # 回溯指定天数
        for i in range(days):
            date = today - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            file_path = self.memory_dir / f"{date_str}.md"
            
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                memories.append(content)
        
        # 用分隔符合并
        return "\n\n---\n\n".join(memories)
    
    def list_memory_files(self) -> list[Path]:
        """列出所有记忆文件。

        Returns:
            所有每日笔记文件路径列表，按日期倒序排列（最新的在前）
        """
        if not self.memory_dir.exists():
            return []
        
        # 匹配 YYYY-MM-DD.md 格式的文件
        files = list(self.memory_dir.glob("????-??-??.md"))
        return sorted(files, reverse=True)
    
    def get_memory_context(self) -> str:
        """获取记忆上下文（用于 LLM 提示词）。

        组合长期记忆和今日笔记，格式化输出。

        Returns:
            格式化的记忆上下文，包含长期记忆和今日笔记
            如果没有记忆，返回空字符串
        """
        parts = []
        
        # 长期记忆
        long_term = self.read_long_term()
        if long_term:
            parts.append("## Long-term Memory\n" + long_term)
        
        # 今日笔记
        today = self.read_today()
        if today:
            parts.append("## Today's Notes\n" + today)
        
        return "\n\n".join(parts) if parts else ""
