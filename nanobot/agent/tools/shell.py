"""Shell 执行工具模块。

提供安全的 Shell 命令执行功能：
- ExecTool: 执行 shell 命令

安全特性：
- 危险命令拦截（rm -rf, format, dd 等）
- 超时控制（默认 60 秒）
- 路径限制（限制在工作区内）
- 输出截断（防止过长输出）
- 白名单/黑名单模式

使用场景：
- 运行 git 命令
- 执行构建脚本
- 系统信息查询
"""

import asyncio
import os
import re
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool


class ExecTool(Tool):
    """Shell 命令执行工具。

    安全执行 shell 命令，具有以下保护机制：

    1. 危险命令拦截：
       - rm -rf（递归删除）
       - format/mkfs（格式化）
       - dd（磁盘写入）
       - shutdown/reboot（关机）
       - fork bomb（:(){ :|:& };:）

    2. 路径限制（可选）：
       - 阻止路径穿越（../）
       - 限制在工作区内

    3. 输出控制：
       - 超时控制（默认 60 秒）
       - 输出截断（最大 10000 字符）

    配置选项：
    - timeout: 命令执行超时时间
    - working_dir: 默认工作目录
    - deny_patterns: 额外的禁止模式（正则）
    - allow_patterns: 白名单模式（启用时只放行匹配命令）
    - restrict_to_workspace: 是否限制在工作区
    """

    def __init__(
        self,
        timeout: int = 60,
        working_dir: str | None = None,
        deny_patterns: list[str] | None = None,
        allow_patterns: list[str] | None = None,
        restrict_to_workspace: bool = False,
    ):
        """初始化 ExecTool。

        Args:
            timeout: 命令执行超时时间（秒），默认 60
            working_dir: 默认工作目录
            deny_patterns: 额外的禁止命令正则列表
            allow_patterns: 白名单正则列表（启用时只执行匹配命令）
            restrict_to_workspace: 是否限制命令在工作区内执行
        """
        self.timeout = timeout
        self.working_dir = working_dir
        # 默认危险命令模式
        self.deny_patterns = deny_patterns or [
            r"\brm\s+-[rf]{1,2}\b",          # rm -r, rm -rf, rm -fr
            r"\bdel\s+/[fq]\b",              # del /f, del /q (Windows)
            r"\brmdir\s+/s\b",               # rmdir /s (Windows)
            r"\b(format|mkfs|diskpart)\b",   # 磁盘操作
            r"\bdd\s+if=",                   # dd 命令
            r">\s*/dev/sd",                  # 直接写入磁盘
            r"\b(shutdown|reboot|poweroff)\b",  # 系统电源
            r":\(\)\s*\{.*\};\s*:",          # fork bomb
        ]
        self.allow_patterns = allow_patterns or []
        self.restrict_to_workspace = restrict_to_workspace
    
    @property
    def name(self) -> str:
        """工具名称。"""
        return "exec"
    
    @property
    def description(self) -> str:
        """工具描述。

        Returns:
            描述文本，提醒 LLM 谨慎使用
        """
        return "Execute a shell command and return its output. Use with caution."
    
    @property
    def parameters(self) -> dict[str, Any]:
        """参数定义。

        Returns:
            JSON Schema，包含 command 和可选的 working_dir
        """
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 shell 命令"
                },
                "working_dir": {
                    "type": "string",
                    "description": "命令执行的工作目录（可选）"
                }
            },
            "required": ["command"]
        }
    
    async def execute(self, command: str, working_dir: str | None = None, **kwargs: Any) -> str:
        """执行 shell 命令。

        执行流程：
        1. 安全检查（_guard_command）
        2. 创建子进程执行命令
        3. 等待输出（带超时）
        4. 格式化输出结果
        5. 截断过长输出

        Args:
            command: 要执行的 shell 命令
            working_dir: 工作目录（可选，覆盖默认）

        Returns:
            命令输出（stdout + stderr），或错误信息
        """
        # 确定工作目录
        cwd = working_dir or self.working_dir or os.getcwd()
        
        # 安全检查
        guard_error = self._guard_command(command, cwd)
        if guard_error:
            return guard_error
        
        try:
            # 创建子进程
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            
            try:
                # 等待执行结果（带超时）
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout
                )
            except asyncio.TimeoutError:
                # 超时杀死进程
                process.kill()
                return f"Error: Command timed out after {self.timeout} seconds"
            
            # 组装输出
            output_parts = []
            
            # 标准输出
            if stdout:
                output_parts.append(stdout.decode("utf-8", errors="replace"))
            
            # 标准错误
            if stderr:
                stderr_text = stderr.decode("utf-8", errors="replace")
                if stderr_text.strip():
                    output_parts.append(f"STDERR:\n{stderr_text}")
            
            # 退出码
            if process.returncode != 0:
                output_parts.append(f"\nExit code: {process.returncode}")
            
            result = "\n".join(output_parts) if output_parts else "(no output)"
            
            # 截断过长输出（防止消息过大）
            max_len = 10000
            if len(result) > max_len:
                result = result[:max_len] + f"\n... (truncated, {len(result) - max_len} more chars)"
            
            return result
            
        except Exception as e:
            return f"Error executing command: {str(e)}"

    def _guard_command(self, command: str, cwd: str) -> str | None:
        """命令安全检查。

        多层防护：
        1. 黑名单检查：匹配 deny_patterns 则拦截
        2. 白名单检查：如果设置了 allow_patterns，不匹配则拦截
        3. 路径检查：如果 restrict_to_workspace，检查路径穿越和越界

        Args:
            command: 要检查的命令
            cwd: 当前工作目录

        Returns:
            如果命令被拦截，返回错误信息；否则返回 None
        """
        cmd = command.strip()
        lower = cmd.lower()

        # 1. 黑名单检查
        for pattern in self.deny_patterns:
            if re.search(pattern, lower):
                return "Error: Command blocked by safety guard (dangerous pattern detected)"

        # 2. 白名单检查（如果设置了）
        if self.allow_patterns:
            if not any(re.search(p, lower) for p in self.allow_patterns):
                return "Error: Command blocked by safety guard (not in allowlist)"

        # 3. 工作区限制
        if self.restrict_to_workspace:
            # 检查路径穿越
            if "..\\" in cmd or "../" in cmd:
                return "Error: Command blocked by safety guard (path traversal detected)"

            cwd_path = Path(cwd).resolve()

            # 提取命令中的路径（Windows 和 POSIX）
            win_paths = re.findall(r"[A-Za-z]:\\[^\\\"']+", cmd)
            posix_paths = re.findall(r"/[^\s\"']+", cmd)

            # 检查每个路径是否在工作区内
            for raw in win_paths + posix_paths:
                try:
                    p = Path(raw).resolve()
                except Exception:
                    continue
                if cwd_path not in p.parents and p != cwd_path:
                    return "Error: Command blocked by safety guard (path outside working dir)"

        return None
