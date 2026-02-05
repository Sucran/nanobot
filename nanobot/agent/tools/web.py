"""Web 工具模块。

提供网络搜索和网页抓取功能：
- WebSearchTool: 使用 Brave Search API 进行网络搜索
- WebFetchTool: 抓取网页并提取可读内容

安全特性：
- URL 验证（只允许 http/https）
- 重定向限制（防止 DoS）
- 内容长度限制
- HTML 标签清理

依赖：
- httpx: 异步 HTTP 客户端
- readability-lxml: 网页内容提取
"""

import html
import json
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from nanobot.agent.tools.base import Tool

# 共享常量
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36"
MAX_REDIRECTS = 5  # 限制重定向次数，防止 DoS 攻击


def _strip_tags(text: str) -> str:
    """移除 HTML 标签并解码实体。

    Args:
        text: 包含 HTML 标签的文本

    Returns:
        纯文本，已解码 HTML 实体
    """
    text = re.sub(r'<script[\s\S]*?</script>', '', text, flags=re.I)  # 移除脚本
    text = re.sub(r'<style[\s\S]*?</style>', '', text, flags=re.I)    # 移除样式
    text = re.sub(r'<[^>]+>', '', text)                               # 移除所有标签
    return html.unescape(text).strip()


def _normalize(text: str) -> str:
    """规范化空白字符。

    Args:
        text: 原始文本

    Returns:
        规范化后的文本（连续空格和空行压缩）
    """
    text = re.sub(r'[ \t]+', ' ', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def _validate_url(url: str) -> tuple[bool, str]:
    """验证 URL 格式。

    检查项：
    - 协议必须是 http 或 https
    - 必须有有效的域名

    Args:
        url: 要验证的 URL

    Returns:
        (是否有效, 错误信息)
    """
    try:
        p = urlparse(url)
        if p.scheme not in ('http', 'https'):
            return False, f"只允许 http/https，当前为 '{p.scheme or 'none'}'"
        if not p.netloc:
            return False, "缺少域名"
        return True, ""
    except Exception as e:
        return False, str(e)


class WebSearchTool(Tool):
    """网络搜索工具。

    使用 Brave Search API 进行网络搜索。
    需要配置 BRAVE_API_KEY 环境变量或在初始化时提供。

    返回结果：
    - 标题
    - URL
    - 摘要描述

    使用示例：
        result = await web_search(query="Python asyncio tutorial", count=5)
    """
    
    name = "web_search"
    description = "Search the web. Returns titles, URLs, and snippets."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "count": {"type": "integer", "description": "返回结果数量 (1-10)", "minimum": 1, "maximum": 10}
        },
        "required": ["query"]
    }
    
    def __init__(self, api_key: str | None = None, max_results: int = 5):
        """初始化搜索工具。

        Args:
            api_key: Brave Search API Key（可选，也可从环境变量获取）
            max_results: 默认返回结果数
        """
        self.api_key = api_key or os.environ.get("BRAVE_API_KEY", "")
        self.max_results = max_results
    
    async def execute(self, query: str, count: int | None = None, **kwargs: Any) -> str:
        """执行网络搜索。

        Args:
            query: 搜索关键词
            count: 返回结果数量（1-10，可选）

        Returns:
            格式化的搜索结果，或错误信息
        """
        if not self.api_key:
            return "Error: BRAVE_API_KEY not configured"
        
        try:
            # 限制结果数量
            n = min(max(count or self.max_results, 1), 10)
            
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": n},
                    headers={"Accept": "application/json", "X-Subscription-Token": self.api_key},
                    timeout=10.0
                )
                r.raise_for_status()
            
            results = r.json().get("web", {}).get("results", [])
            if not results:
                return f"No results for: {query}"
            
            # 格式化输出
            lines = [f"Results for: {query}\n"]
            for i, item in enumerate(results[:n], 1):
                lines.append(f"{i}. {item.get('title', '')}\n   {item.get('url', '')}")
                if desc := item.get("description"):
                    lines.append(f"   {desc}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"


class WebFetchTool(Tool):
    """网页抓取工具。

    抓取指定 URL 的内容，并提取可读文本。

    支持格式：
    - HTML → Markdown（使用 Readability 提取正文）
    - HTML → 纯文本（提取文本内容）
    - JSON（直接格式化）

    安全特性：
    - URL 验证
    - 重定向限制
    - 内容长度限制

    使用示例：
        result = await web_fetch(url="https://example.com", extractMode="markdown")
    """
    
    name = "web_fetch"
    description = "Fetch URL and extract readable content (HTML → markdown/text)."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要抓取的 URL"},
            "extractMode": {"type": "string", "enum": ["markdown", "text"], "default": "markdown", "description": "提取模式"},
            "maxChars": {"type": "integer", "minimum": 100, "description": "最大字符数"}
        },
        "required": ["url"]
    }
    
    def __init__(self, max_chars: int = 50000):
        """初始化抓取工具。

        Args:
            max_chars: 默认最大返回字符数
        """
        self.max_chars = max_chars
    
    async def execute(self, url: str, extractMode: str = "markdown", maxChars: int | None = None, **kwargs: Any) -> str:
        """执行网页抓取。

        抓取流程：
        1. 验证 URL 格式
        2. 发送 HTTP GET 请求
        3. 根据内容类型处理：
           - JSON: 直接格式化
           - HTML: 使用 Readability 提取正文
           - 其他: 返回原始文本
        4. 截断过长内容
        5. 返回结构化结果

        Args:
            url: 要抓取的 URL
            extractMode: 提取模式（"markdown" 或 "text"）
            maxChars: 最大字符数（可选）

        Returns:
            JSON 格式的抓取结果，包含 url、status、text 等字段
        """
        from readability import Document

        max_chars = maxChars or self.max_chars

        # 验证 URL
        is_valid, error_msg = _validate_url(url)
        if not is_valid:
            return json.dumps({"error": f"URL validation failed: {error_msg}", "url": url})

        try:
            # 创建 HTTP 客户端（带重定向限制）
            async with httpx.AsyncClient(
                follow_redirects=True,
                max_redirects=MAX_REDIRECTS,
                timeout=30.0
            ) as client:
                r = await client.get(url, headers={"User-Agent": USER_AGENT})
                r.raise_for_status()
            
            ctype = r.headers.get("content-type", "")
            
            # 根据内容类型处理
            if "application/json" in ctype:
                # JSON 内容
                text, extractor = json.dumps(r.json(), indent=2), "json"
            elif "text/html" in ctype or r.text[:256].lower().startswith(("<!doctype", "<html")):
                # HTML 内容
                doc = Document(r.text)
                if extractMode == "markdown":
                    content = self._to_markdown(doc.summary())
                else:
                    content = _strip_tags(doc.summary())
                text = f"# {doc.title()}\n\n{content}" if doc.title() else content
                extractor = "readability"
            else:
                # 其他内容
                text, extractor = r.text, "raw"
            
            # 截断过长内容
            truncated = len(text) > max_chars
            if truncated:
                text = text[:max_chars]
            
            return json.dumps({
                "url": url,
                "finalUrl": str(r.url),
                "status": r.status_code,
                "extractor": extractor,
                "truncated": truncated,
                "length": len(text),
                "text": text
            })
        except Exception as e:
            return json.dumps({"error": str(e), "url": url})
    
    def _to_markdown(self, html: str) -> str:
        """将 HTML 转换为 Markdown。

        转换规则：
        - 链接: <a> → [text](url)
        - 标题: <h1-6> → # Heading
        - 列表: <li> → - item
        - 段落: <p> → 空行分隔
        - 换行: <br> → \n

        Args:
            html: HTML 内容

        Returns:
            Markdown 格式文本
        """
        # 转换链接
        text = re.sub(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
                      lambda m: f'[{_strip_tags(m[2])}]({m[1]})', html, flags=re.I)
        # 转换标题
        text = re.sub(r'<h([1-6])[^>]*>([\s\S]*?)</h\1>',
                      lambda m: f'\n{"#" * int(m[1])} {_strip_tags(m[2])}\n', text, flags=re.I)
        # 转换列表项
        text = re.sub(r'<li[^>]*>([\s\S]*?)</li>', lambda m: f'\n- {_strip_tags(m[1])}', text, flags=re.I)
        # 段落和区块结束
        text = re.sub(r'</(p|div|section|article)>', '\n\n', text, flags=re.I)
        # 换行
        text = re.sub(r'<(br|hr)\s*/?>', '\n', text, flags=re.I)
        return _normalize(_strip_tags(text))
