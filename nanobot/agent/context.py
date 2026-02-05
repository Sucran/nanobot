"""上下文构建器：组装代理提示词。

此模块负责构建发送给 LLM 的完整上下文，包括：
- 系统提示词（Bootstrap 文件、身份信息）
- 记忆内容（长期记忆和短期记忆）
- 技能信息（内置技能和自定义技能）
- 对话历史

通过渐进式加载策略，核心技能完整加载，普通技能只显示摘要。
"""

import base64
import mimetypes
from pathlib import Path
from typing import Any

from nanobot.agent.memory import MemoryStore
from nanobot.agent.skills import SkillsLoader


class ContextBuilder:
    """
    上下文构建器。

    负责组装发送给 LLM 的完整上下文，包含以下部分：
    1. 核心身份信息 - 机器人的基本描述和当前时间
    2. Bootstrap 文件 - AGENTS.md, SOUL.md, USER.md, TOOLS.md, IDENTITY.md
    3. 记忆内容 - 从 memory/MEMORY.md 和最近几天的笔记中获取
    4. 技能信息 - 渐进式加载，核心技能完整加载，其他技能只显示摘要

    技能来源优先级：工作区 > 内置技能
    """

    # Bootstrap 文件名列表，按顺序加载
    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md"]

    def __init__(self, workspace: Path):
        """初始化上下文构建器。

        Args:
            workspace: 工作区目录路径
        """
        self.workspace = workspace
        self.memory = MemoryStore(workspace)  # 记忆存储
        self.skills = SkillsLoader(workspace)  # 技能加载器
    
    def build_system_prompt(self, skill_names: list[str] | None = None) -> str:
        """构建完整的系统提示词。

        按以下顺序组装上下文：
        1. 核心身份信息 - 机器人描述、当前时间、工作区路径
        2. Bootstrap 文件 - AGENTS.md、SOUL.md 等配置文件
        3. 记忆内容 - 从 memory/MEMORY.md 获取相关记忆
        4. 技能信息 - 渐进式加载（核心技能完整，其他技能只显示摘要）

        渐进式加载策略：
        - Always Skills: 完整加载到系统提示词
        - Available Skills: 只显示摘要，Agent 按需读取

        Args:
            skill_names: 要包含的技能名称列表（可选）

        Returns:
            完整的系统提示词字符串，包含所有上下文信息
        """
        parts = []
        
        # 1. 核心身份信息
        parts.append(self._get_identity())
        
        # 2. Bootstrap 配置文件
        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            parts.append(bootstrap)
        
        # 3. 记忆内容
        memory = self.memory.get_memory_context()
        if memory:
            parts.append(f"# Memory\n\n{memory}")
        
        # 4. 技能信息 - 渐进式加载
        # Always Skills: 完整内容
        always_skills = self.skills.get_always_skills()
        if always_skills:
            always_content = self.skills.load_skills_for_context(always_skills)
            if always_content:
                parts.append(f"# Active Skills\n\n{always_content}")
        
        # Available Skills: 只显示摘要
        skills_summary = self.skills.build_skills_summary()
        if skills_summary:
            parts.append(f"""# Skills

The following skills extend your capabilities. To use a skill, read its SKILL.md file using the read_file tool.
Skills with available="false" need dependencies installed first - you can try installing them with apt/brew.

{skills_summary}""")
        
        return "\n\n---\n\n".join(parts)
    
    def _get_identity(self) -> str:
        """构建核心身份信息部分。

        包含：
        - 机器人名称和描述
        - 可用工具列表
        - 当前时间
        - 工作区路径
        - 重要提示（如何响应消息、何时使用工具等）

        Returns:
            格式化的身份信息字符串，用于系统提示词开头
        """
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        workspace_path = str(self.workspace.expanduser().resolve())
        
        return f"""# nanobot 🐈

You are nanobot, a helpful AI assistant. You have access to tools that allow you to:
- Read, write, and edit files
- Execute shell commands
- Search the web and fetch web pages
- Send messages to users on chat channels
- Spawn subagents for complex background tasks

## Current Time
{now}

## Workspace
Your workspace is at: {workspace_path}
- Memory files: {workspace_path}/memory/MEMORY.md
- Daily notes: {workspace_path}/memory/YYYY-MM-DD.md
- Custom skills: {workspace_path}/skills/{{skill-name}}/SKILL.md

IMPORTANT: When responding to direct questions or conversations, reply directly with your text response.
Only use the 'message' tool when you need to send a message to a specific chat channel (like WhatsApp).
For normal conversation, just respond with text - do not call the message tool.

Always be helpful, accurate, and concise. When using tools, explain what you're doing.
When remembering something, write to {workspace_path}/memory/MEMORY.md"""
    
    def _load_bootstrap_files(self) -> str:
        """加载所有 Bootstrap 配置文件。

        按 BOOTSTRAP_FILES 定义的顺序加载：
        1. AGENTS.md - Agent 说明
        2. SOUL.md - 机器人人格
        3. USER.md - 用户信息
        4. TOOLS.md - 工具说明
        5. IDENTITY.md - 身份定义

        Returns:
            格式化的 Bootstrap 内容字符串，格式为 "## filename\\n\\ncontent"
            如果所有文件都不存在，返回空字符串
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
    ) -> list[dict[str, Any]]:
        """构建完整的消息列表，用于 LLM 调用。

        消息结构：
        1. System Message - 系统提示词
        2. History Messages - 历史对话
        3. User Message - 当前用户消息（含图片附件）

        Args:
            history: 历史对话消息列表，每条消息包含 role 和 content
            current_message: 当前用户发送的消息内容
            skill_names: 要激活的技能名称列表（可选）
            media: 本地图片/媒体文件路径列表（可选）

        Returns:
            完整的消息列表，可直接传给 LLM 的 messages 参数
        """
        messages = []

        # 1. 系统提示词
        system_prompt = self.build_system_prompt(skill_names)
        messages.append({"role": "system", "content": system_prompt})

        # 2. 对话历史
        messages.extend(history)

        # 3. 当前消息（支持图片附件）
        user_content = self._build_user_content(current_message, media)
        messages.append({"role": "user", "content": user_content})

        return messages

    def _build_user_content(self, text: str, media: list[str] | None) -> str | list[dict[str, Any]]:
        """构建用户消息内容，支持 Base64 编码的图片附件。

        图片处理流程：
        1. 检查文件是否存在
        2. 猜测 MIME 类型（只处理图片）
        3. 读取文件并 Base64 编码
        4. 构建 OpenAI 格式的图片对象

        Args:
            text: 文本消息内容
            media: 本地图片文件路径列表

        Returns:
            如果无图片：返回原始文本
            如果有图片：返回混合格式 [{图片对象}, {文本对象}]
        """
        if not media:
            return text
        
        images = []
        for path in media:
            p = Path(path)
            mime, _ = mimetypes.guess_type(path)
            # 只处理图片文件
            if not p.is_file() or not mime or not mime.startswith("image/"):
                continue
            # Base64 编码图片
            b64 = base64.b64encode(p.read_bytes()).decode()
            images.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
        
        if not images:
            return text
        return images + [{"type": "text", "text": text}]
    
    def add_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        tool_name: str,
        result: str
    ) -> list[dict[str, Any]]:
        """将工具执行结果添加到消息列表。

        在 ReAct 模式中，工具执行完成后需要将结果返回给 LLM。
        使用 tool 角色标记，LLM 可以看到工具调用和结果。

        Args:
            messages: 当前消息列表
            tool_call_id: 工具调用的 ID（来自 LLM 的 tool_calls[].id）
            tool_name: 工具名称
            result: 工具执行结果

        Returns:
            添加工具结果后的消息列表
        """
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result
        })
        return messages
    
    def add_assistant_message(
        self,
        messages: list[dict[str, Any]],
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None
    ) -> list[dict[str, Any]]:
        """将助手消息添加到消息列表。

        用于记录 LLM 的响应（或工具调用决策）。

        Args:
            messages: 当前消息列表
            content: 助手消息内容（可为 None，如果只有工具调用）
            tool_calls: 工具调用列表（可选，用于函数调用场景）

        Returns:
            添加助手消息后的消息列表
        """
        msg: dict[str, Any] = {"role": "assistant", "content": content or ""}
        
        if tool_calls:
            msg["tool_calls"] = tool_calls
        
        messages.append(msg)
        return messages
