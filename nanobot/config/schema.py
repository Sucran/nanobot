"""配置模式模块。

使用 Pydantic 定义 nanobot 的配置结构，支持：
- 类型验证
- 环境变量加载
- 默认值
- 嵌套配置

环境变量格式：
- 顶层: NANOBOT_KEY=value
- 嵌套: NANOBOT_SECTION__KEY=value

示例：
    NANOBOT_AGENTS__DEFAULTS__MODEL=openai/gpt-4
    NANOBOT_PROVIDERS__ANTHROPIC__API_KEY=sk-xxx
"""

from pathlib import Path
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class WhatsAppConfig(BaseModel):
    """WhatsApp 渠道配置。

    Attributes:
        enabled: 是否启用 WhatsApp 渠道
        bridge_url: WhatsApp Bridge WebSocket 地址
        allow_from: 允许的用户手机号列表（空列表表示允许所有）
    """
    enabled: bool = False
    bridge_url: str = "ws://localhost:3001"
    allow_from: list[str] = Field(default_factory=list)


class TelegramConfig(BaseModel):
    """Telegram 渠道配置。

    Attributes:
        enabled: 是否启用 Telegram 渠道
        token: Bot Token（从 @BotFather 获取）
        allow_from: 允许的用户 ID 或用户名列表
    """
    enabled: bool = False
    token: str = ""  # 从 @BotFather 获取的 Bot Token
    allow_from: list[str] = Field(default_factory=list)


class ChannelsConfig(BaseModel):
    """聊天渠道配置集合。

    包含所有支持的聊天渠道配置。
    """
    whatsapp: WhatsAppConfig = Field(default_factory=WhatsAppConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)


class AgentDefaults(BaseModel):
    """Agent 默认配置。

    Attributes:
        workspace: 工作区目录路径
        model: 默认使用的 LLM 模型
        max_tokens: 最大生成 token 数
        temperature: 采样温度（0-1）
        max_tool_iterations: 最大工具迭代次数
    """
    workspace: str = "~/.nanobot/workspace"
    model: str = "anthropic/claude-opus-4-5"
    max_tokens: int = 8192
    temperature: float = 0.7
    max_tool_iterations: int = 20


class AgentsConfig(BaseModel):
    """Agent 配置。"""
    defaults: AgentDefaults = Field(default_factory=AgentDefaults)


class ProviderConfig(BaseModel):
    """LLM 提供商配置。

    Attributes:
        api_key: API 密钥
        api_base: API 基础 URL（可选，用于自定义端点）
    """
    api_key: str = ""
    api_base: str | None = None


class ProvidersConfig(BaseModel):
    """LLM 提供商配置集合。

    支持多个提供商，按优先级自动选择（有 API key 的第一个）。
    """
    anthropic: ProviderConfig = Field(default_factory=ProviderConfig)
    openai: ProviderConfig = Field(default_factory=ProviderConfig)
    openrouter: ProviderConfig = Field(default_factory=ProviderConfig)
    groq: ProviderConfig = Field(default_factory=ProviderConfig)
    zhipu: ProviderConfig = Field(default_factory=ProviderConfig)
    vllm: ProviderConfig = Field(default_factory=ProviderConfig)
    gemini: ProviderConfig = Field(default_factory=ProviderConfig)


class GatewayConfig(BaseModel):
    """Gateway 服务器配置。

    Attributes:
        host: 监听地址
        port: 监听端口
    """
    host: str = "0.0.0.0"
    port: int = 18790


class WebSearchConfig(BaseModel):
    """网络搜索工具配置。

    Attributes:
        api_key: Brave Search API 密钥
        max_results: 默认返回结果数
    """
    api_key: str = ""
    max_results: int = 5


class WebToolsConfig(BaseModel):
    """Web 工具配置集合。"""
    search: WebSearchConfig = Field(default_factory=WebSearchConfig)


class ExecToolConfig(BaseModel):
    """Shell 执行工具配置。

    Attributes:
        timeout: 命令执行超时时间（秒）
        restrict_to_workspace: 是否限制命令只能访问工作区内的路径
    """
    timeout: int = 60
    restrict_to_workspace: bool = False


class ToolsConfig(BaseModel):
    """工具配置集合。"""
    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)


class Config(BaseSettings):
    """nanobot 根配置。

    支持从环境变量加载配置，前缀为 NANOBOT_。
    嵌套配置使用 __ 分隔，如 NANOBOT_AGENTS__DEFAULTS__MODEL。

    Attributes:
        agents: Agent 配置
        channels: 聊天渠道配置
        providers: LLM 提供商配置
        gateway: Gateway 服务器配置
        tools: 工具配置
    """
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    
    @property
    def workspace_path(self) -> Path:
        """获取展开后的工作区路径。

        Returns:
            Path 对象，~ 符号已展开
        """
        return Path(self.agents.defaults.workspace).expanduser()
    
    def get_api_key(self) -> str | None:
        """按优先级获取 API 密钥。

        优先级顺序：OpenRouter > Anthropic > OpenAI > Gemini > Zhipu > Groq > vLLM

        Returns:
            第一个找到的 API 密钥，如果没有则返回 None
        """
        return (
            self.providers.openrouter.api_key or
            self.providers.anthropic.api_key or
            self.providers.openai.api_key or
            self.providers.gemini.api_key or
            self.providers.zhipu.api_key or
            self.providers.groq.api_key or
            self.providers.vllm.api_key or
            None
        )
    
    def get_api_base(self) -> str | None:
        """获取 API 基础 URL。

        如果使用 OpenRouter、Zhipu 或 vLLM，返回对应的 API 端点。

        Returns:
            API 基础 URL，如果没有则返回 None
        """
        if self.providers.openrouter.api_key:
            return self.providers.openrouter.api_base or "https://openrouter.ai/api/v1"
        if self.providers.zhipu.api_key:
            return self.providers.zhipu.api_base
        if self.providers.vllm.api_base:
            return self.providers.vllm.api_base
        return None
    
    class Config:
        """Pydantic 配置。"""
        env_prefix = "NANOBOT_"  # 环境变量前缀
        env_nested_delimiter = "__"  # 嵌套分隔符
