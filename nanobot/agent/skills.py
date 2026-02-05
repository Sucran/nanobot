"""技能加载器模块。

管理 Agent 的技能（Skills），技能是教 Agent 如何使用特定工具或执行特定任务的 markdown 文件。

技能来源（优先级从高到低）：
1. 工作区技能: workspace/skills/{skill-name}/SKILL.md
2. 内置技能: nanobot/skills/{skill-name}/SKILL.md

技能元数据（YAML Frontmatter）：
```yaml
---
description: "技能描述"
always: true  # 是否总是加载
metadata: '{"nanobot": {"requires": {"bins": ["cli-tool"], "env": ["API_KEY"]}}}'
---
```

渐进式加载策略：
- 标记为 always=true 的技能：完整内容加载到上下文
- 其他技能：只显示摘要，Agent 按需读取
"""

import json
import os
import re
import shutil
from pathlib import Path

# 内置技能目录（相对于本文件）
BUILTIN_SKILLS_DIR = Path(__file__).parent.parent / "skills"


class SkillsLoader:
    """技能加载器。

    负责发现、加载和管理 Agent 技能。

    功能：
    - 技能发现：扫描工作区和内置技能目录
    - 技能加载：读取 SKILL.md 内容
    - 元数据解析：解析 YAML frontmatter
    - 依赖检查：验证二进制文件和环境变量
    - 渐进式加载：构建技能摘要

    使用示例：
        loader = SkillsLoader(workspace)
        
        # 列出所有可用技能
        skills = loader.list_skills()
        
        # 加载特定技能
        content = loader.load_skill("weather")
        
        # 获取总是加载的技能
        always_skills = loader.get_always_skills()
        
        # 构建技能摘要（用于上下文）
        summary = loader.build_skills_summary()
    """

    def __init__(self, workspace: Path, builtin_skills_dir: Path | None = None):
        """初始化技能加载器。

        Args:
            workspace: 工作区目录路径
            builtin_skills_dir: 内置技能目录（可选，默认使用 BUILTIN_SKILLS_DIR）
        """
        self.workspace = workspace
        # 工作区技能目录（用户自定义技能）
        self.workspace_skills = workspace / "skills"
        # 内置技能目录（系统自带技能）
        self.builtin_skills = builtin_skills_dir or BUILTIN_SKILLS_DIR
    
    def list_skills(self, filter_unavailable: bool = True) -> list[dict[str, str]]:
        """列出所有可用技能。

        按优先级合并工作区技能和内置技能：
        - 工作区技能同名时覆盖内置技能
        - 支持按依赖条件过滤

        Args:
            filter_unavailable: 如果为 True，过滤掉依赖未满足的技能

        Returns:
            技能信息列表，每个元素包含 name、path、source
        """
        skills = []
        
        # 1. 工作区技能（最高优先级）
        if self.workspace_skills.exists():
            for skill_dir in self.workspace_skills.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        skills.append({
                            "name": skill_dir.name,
                            "path": str(skill_file),
                            "source": "workspace"
                        })
        
        # 2. 内置技能（只添加不存在于工作区的）
        if self.builtin_skills and self.builtin_skills.exists():
            for skill_dir in self.builtin_skills.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists() and not any(s["name"] == skill_dir.name for s in skills):
                        skills.append({
                            "name": skill_dir.name,
                            "path": str(skill_file),
                            "source": "builtin"
                        })
        
        # 按依赖过滤
        if filter_unavailable:
            return [s for s in skills if self._check_requirements(self._get_skill_meta(s["name"]))]
        return skills
    
    def load_skill(self, name: str) -> str | None:
        """加载指定技能的内容。

        按优先级查找：
        1. 工作区技能
        2. 内置技能

        Args:
            name: 技能名称（目录名）

        Returns:
            SKILL.md 的内容，如果找不到返回 None
        """
        # 优先检查工作区
        workspace_skill = self.workspace_skills / name / "SKILL.md"
        if workspace_skill.exists():
            return workspace_skill.read_text(encoding="utf-8")
        
        # 检查内置技能
        if self.builtin_skills:
            builtin_skill = self.builtin_skills / name / "SKILL.md"
            if builtin_skill.exists():
                return builtin_skill.read_text(encoding="utf-8")
        
        return None
    
    def load_skills_for_context(self, skill_names: list[str]) -> str:
        """加载指定技能的内容，用于构建 Agent 上下文。

        移除 YAML frontmatter，格式化为上下文可用格式。

        Args:
            skill_names: 要加载的技能名称列表

        Returns:
            格式化的技能内容，多个技能用分隔符分隔
        """
        parts = []
        for name in skill_names:
            content = self.load_skill(name)
            if content:
                # 移除 frontmatter
                content = self._strip_frontmatter(content)
                parts.append(f"### Skill: {name}\n\n{content}")
        
        return "\n\n---\n\n".join(parts) if parts else ""
    
    def build_skills_summary(self) -> str:
        """构建所有技能的摘要（XML 格式）。

        用于渐进式加载：Agent 看到摘要后，可以通过 read_file 按需读取完整内容。

        返回格式：
        ```xml
        <skills>
          <skill available="true">
            <name>weather</name>
            <description>查询天气</description>
            <location>/path/to/SKILL.md</location>
          </skill>
        </skills>
        ```

        Returns:
            XML 格式的技能摘要
        """
        all_skills = self.list_skills(filter_unavailable=False)
        if not all_skills:
            return ""
        
        def escape_xml(s: str) -> str:
            """XML 转义"""
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        lines = ["<skills>"]
        for s in all_skills:
            name = escape_xml(s["name"])
            path = s["path"]
            desc = escape_xml(self._get_skill_description(s["name"]))
            skill_meta = self._get_skill_meta(s["name"])
            available = self._check_requirements(skill_meta)
            
            lines.append(f'  <skill available="{str(available).lower()}">')
            lines.append(f"    <name>{name}</name>")
            lines.append(f"    <description>{desc}</description>")
            lines.append(f"    <location>{path}</location>")
            
            # 显示未满足的依赖
            if not available:
                missing = self._get_missing_requirements(skill_meta)
                if missing:
                    lines.append(f"    <requires>{escape_xml(missing)}</requires>")
            
            lines.append(f"  </skill>")
        lines.append("</skills>")
        
        return "\n".join(lines)
    
    def _get_missing_requirements(self, skill_meta: dict) -> str:
        """获取未满足的依赖描述。

        Args:
            skill_meta: 技能元数据

        Returns:
            缺失的依赖列表（逗号分隔）
        """
        missing = []
        requires = skill_meta.get("requires", {})
        
        # 检查二进制命令
        for b in requires.get("bins", []):
            if not shutil.which(b):
                missing.append(f"CLI: {b}")
        
        # 检查环境变量
        for env in requires.get("env", []):
            if not os.environ.get(env):
                missing.append(f"ENV: {env}")
        
        return ", ".join(missing)
    
    def _get_skill_description(self, name: str) -> str:
        """获取技能描述。

        从 frontmatter 中读取 description 字段。

        Args:
            name: 技能名称

        Returns:
            描述文本，如果没有则返回技能名
        """
        meta = self.get_skill_metadata(name)
        if meta and meta.get("description"):
            return meta["description"]
        return name  # 回退到技能名
    
    def _strip_frontmatter(self, content: str) -> str:
        """移除 YAML frontmatter。

        Args:
            content: 原始内容

        Returns:
            移除 frontmatter 后的内容
        """
        if content.startswith("---"):
            match = re.match(r"^---\n.*?\n---\n", content, re.DOTALL)
            if match:
                return content[match.end():].strip()
        return content
    
    def _parse_nanobot_metadata(self, raw: str) -> dict:
        """解析 nanobot 元数据 JSON。

        Args:
            raw: metadata 字段的原始字符串

        Returns:
            解析后的字典
        """
        try:
            data = json.loads(raw)
            return data.get("nanobot", {}) if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def _check_requirements(self, skill_meta: dict) -> bool:
        """检查技能依赖是否满足。

        检查项：
        - bins: 二进制命令是否存在
        - env: 环境变量是否设置

        Args:
            skill_meta: 技能元数据

        Returns:
            True 如果所有依赖都满足
        """
        requires = skill_meta.get("requires", {})
        
        # 检查二进制
        for b in requires.get("bins", []):
            if not shutil.which(b):
                return False
        
        # 检查环境变量
        for env in requires.get("env", []):
            if not os.environ.get(env):
                return False
        
        return True
    
    def _get_skill_meta(self, name: str) -> dict:
        """获取技能的 nanobot 元数据。

        Args:
            name: 技能名称

        Returns:
            nanobot 元数据字典
        """
        meta = self.get_skill_metadata(name) or {}
        return self._parse_nanobot_metadata(meta.get("metadata", ""))
    
    def get_always_skills(self) -> list[str]:
        """获取标记为 always=true 且依赖满足的技能。

        Returns:
            总是加载的技能名称列表
        """
        result = []
        for s in self.list_skills(filter_unavailable=True):
            meta = self.get_skill_metadata(s["name"]) or {}
            skill_meta = self._parse_nanobot_metadata(meta.get("metadata", ""))
            # 检查 always 标记（支持 frontmatter 顶层或 metadata 内）
            if skill_meta.get("always") or meta.get("always"):
                result.append(s["name"])
        return result
    
    def get_skill_metadata(self, name: str) -> dict | None:
        """从技能的 frontmatter 获取元数据。

        Args:
            name: 技能名称

        Returns:
            元数据字典，如果没有 frontmatter 返回 None
        """
        content = self.load_skill(name)
        if not content:
            return None
        
        # 解析 YAML frontmatter
        if content.startswith("---"):
            match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if match:
                # 简单 YAML 解析（只支持 key: value 格式）
                metadata = {}
                for line in match.group(1).split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        metadata[key.strip()] = value.strip().strip('"\'')
                return metadata
        
        return None
