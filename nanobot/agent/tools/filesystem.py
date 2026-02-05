"""文件系统工具模块。

提供基本的文件读写操作工具：
- ReadFileTool: 读取文件内容
- WriteFileTool: 写入文件内容
- EditFileTool: 编辑文件（替换文本）
- ListDirTool: 列出目录内容

安全特性：
- 自动展开 ~ 符号
- 路径验证（文件/目录检查）
- 权限错误处理
- 编码处理（UTF-8）
"""

from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool


class ReadFileTool(Tool):
    """读取文件工具。

    用于读取本地文件的内容，支持：
    - UTF-8 编码文件
    - 路径展开（~ 符号）
    - 错误处理（文件不存在、权限问题等）

    使用示例：
        result = await read_file(path="/path/to/file.txt")
    """

    @property
    def name(self) -> str:
        """工具名称。"""
        return "read_file"
    
    @property
    def description(self) -> str:
        """工具描述。

        Returns:
            描述文本，告诉 LLM 这个工具可以读取文件内容
        """
        return "Read the contents of a file at the given path."
    
    @property
    def parameters(self) -> dict[str, Any]:
        """参数定义。

        Returns:
            JSON Schema，包含 path 参数的定义
        """
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要读取的文件路径"
                }
            },
            "required": ["path"]
        }
    
    async def execute(self, path: str, **kwargs: Any) -> str:
        """执行文件读取。

        Args:
            path: 文件路径（支持 ~ 展开）

        Returns:
            文件内容，或错误信息
        """
        try:
            file_path = Path(path).expanduser()
            # 检查文件是否存在
            if not file_path.exists():
                return f"Error: File not found: {path}"
            # 检查是否为文件
            if not file_path.is_file():
                return f"Error: Not a file: {path}"
            
            # 读取内容
            content = file_path.read_text(encoding="utf-8")
            return content
        except PermissionError:
            return f"Error: Permission denied: {path}"
        except Exception as e:
            return f"Error reading file: {str(e)}"


class WriteFileTool(Tool):
    """写入文件工具。

    用于创建或覆盖文件内容，支持：
    - 自动创建父目录
    - UTF-8 编码
    - 路径展开（~ 符号）

    注意：此工具会覆盖已存在的文件。
    """

    @property
    def name(self) -> str:
        """工具名称。"""
        return "write_file"
    
    @property
    def description(self) -> str:
        """工具描述。

        Returns:
            描述文本，告诉 LLM 这个工具可以写入文件
        """
        return "Write content to a file at the given path. Creates parent directories if needed."
    
    @property
    def parameters(self) -> dict[str, Any]:
        """参数定义。

        Returns:
            JSON Schema，包含 path 和 content 参数
        """
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要写入的文件路径"
                },
                "content": {
                    "type": "string",
                    "description": "要写入的内容"
                }
            },
            "required": ["path", "content"]
        }
    
    async def execute(self, path: str, content: str, **kwargs: Any) -> str:
        """执行文件写入。

        Args:
            path: 文件路径
            content: 要写入的内容

        Returns:
            操作结果（成功字节数或错误信息）
        """
        try:
            file_path = Path(path).expanduser()
            # 自动创建父目录
            file_path.parent.mkdir(parents=True, exist_ok=True)
            # 写入文件
            file_path.write_text(content, encoding="utf-8")
            return f"Successfully wrote {len(content)} bytes to {path}"
        except PermissionError:
            return f"Error: Permission denied: {path}"
        except Exception as e:
            return f"Error writing file: {str(e)}"


class EditFileTool(Tool):
    """编辑文件工具。

    通过精确替换文本来编辑文件。

    特性：
    - 精确匹配：old_text 必须完全匹配
    - 唯一性检查：如果匹配多次会警告
    - 首次替换：只替换第一次出现的位置
    """

    @property
    def name(self) -> str:
        """工具名称。"""
        return "edit_file"
    
    @property
    def description(self) -> str:
        """工具描述。

        Returns:
            描述文本，告诉 LLM 这个工具可以编辑文件
        """
        return "Edit a file by replacing old_text with new_text. The old_text must exist exactly in the file."
    
    @property
    def parameters(self) -> dict[str, Any]:
        """参数定义。

        Returns:
            JSON Schema，包含 path、old_text、new_text
        """
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要编辑的文件路径"
                },
                "old_text": {
                    "type": "string",
                    "description": "要查找并替换的精确文本"
                },
                "new_text": {
                    "type": "string",
                    "description": "要替换成的文本"
                }
            },
            "required": ["path", "old_text", "new_text"]
        }
    
    async def execute(self, path: str, old_text: str, new_text: str, **kwargs: Any) -> str:
        """执行文件编辑。

        Args:
            path: 文件路径
            old_text: 要查找的精确文本
            new_text: 要替换成的文本

        Returns:
            操作结果或错误信息
        """
        try:
            file_path = Path(path).expanduser()
            if not file_path.exists():
                return f"Error: File not found: {path}"
            
            content = file_path.read_text(encoding="utf-8")
            
            # 检查 old_text 是否存在
            if old_text not in content:
                return f"Error: old_text not found in file. Make sure it matches exactly."
            
            # 检查匹配次数
            count = content.count(old_text)
            if count > 1:
                return f"Warning: old_text appears {count} times. Please provide more context to make it unique."
            
            # 执行替换（只替换第一次）
            new_content = content.replace(old_text, new_text, 1)
            file_path.write_text(new_content, encoding="utf-8")
            
            return f"Successfully edited {path}"
        except PermissionError:
            return f"Error: Permission denied: {path}"
        except Exception as e:
            return f"Error editing file: {str(e)}"


class ListDirTool(Tool):
    """列出目录工具。

    列出目录中的所有文件和子目录，支持：
    - 路径展开（~ 符号）
    - 类型标记（📁 目录，📄 文件）
    - 排序输出
    """

    @property
    def name(self) -> str:
        """工具名称。"""
        return "list_dir"
    
    @property
    def description(self) -> str:
        """工具描述。

        Returns:
            描述文本，告诉 LLM 这个工具可以列出目录
        """
        return "List the contents of a directory."
    
    @property
    def parameters(self) -> dict[str, Any]:
        """参数定义。

        Returns:
            JSON Schema，包含 path 参数
        """
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要列出的目录路径"
                }
            },
            "required": ["path"]
        }
    
    async def execute(self, path: str, **kwargs: Any) -> str:
        """执行目录列出。

        Args:
            path: 目录路径

        Returns:
            目录内容列表，或错误信息
        """
        try:
            dir_path = Path(path).expanduser()
            if not dir_path.exists():
                return f"Error: Directory not found: {path}"
            if not dir_path.is_dir():
                return f"Error: Not a directory: {path}"
            
            items = []
            for item in sorted(dir_path.iterdir()):
                prefix = "📁 " if item.is_dir() else "📄 "
                items.append(f"{prefix}{item.name}")
            
            if not items:
                return f"Directory {path} is empty"
            
            return "\n".join(items)
        except PermissionError:
            return f"Error: Permission denied: {path}"
        except Exception as e:
            return f"Error listing directory: {str(e)}"
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to edit"
                },
                "old_text": {
                    "type": "string",
                    "description": "The exact text to find and replace"
                },
                "new_text": {
                    "type": "string",
                    "description": "The text to replace with"
                }
            },
            "required": ["path", "old_text", "new_text"]
        }
    
    async def execute(self, path: str, old_text: str, new_text: str, **kwargs: Any) -> str:
        try:
            file_path = Path(path).expanduser()
            if not file_path.exists():
                return f"Error: File not found: {path}"
            
            content = file_path.read_text(encoding="utf-8")
            
            if old_text not in content:
                return f"Error: old_text not found in file. Make sure it matches exactly."
            
            # Count occurrences
            count = content.count(old_text)
            if count > 1:
                return f"Warning: old_text appears {count} times. Please provide more context to make it unique."
            
            new_content = content.replace(old_text, new_text, 1)
            file_path.write_text(new_content, encoding="utf-8")
            
            return f"Successfully edited {path}"
        except PermissionError:
            return f"Error: Permission denied: {path}"
        except Exception as e:
            return f"Error editing file: {str(e)}"


class ListDirTool(Tool):
    """Tool to list directory contents."""
    
    @property
    def name(self) -> str:
        return "list_dir"
    
    @property
    def description(self) -> str:
        return "List the contents of a directory."
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The directory path to list"
                }
            },
            "required": ["path"]
        }
    
    async def execute(self, path: str, **kwargs: Any) -> str:
        try:
            dir_path = Path(path).expanduser()
            if not dir_path.exists():
                return f"Error: Directory not found: {path}"
            if not dir_path.is_dir():
                return f"Error: Not a directory: {path}"
            
            items = []
            for item in sorted(dir_path.iterdir()):
                prefix = "📁 " if item.is_dir() else "📄 "
                items.append(f"{prefix}{item.name}")
            
            if not items:
                return f"Directory {path} is empty"
            
            return "\n".join(items)
        except PermissionError:
            return f"Error: Permission denied: {path}"
        except Exception as e:
            return f"Error listing directory: {str(e)}"
