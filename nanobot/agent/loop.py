"""Agent 循环模块：核心处理引擎。

代理的主循环，负责处理消息的完整生命周期：
1. 从消息总线接收消息
2. 构建上下文（历史、记忆、技能）
3. 调用 LLM 生成响应
4. 执行工具调用
5. 发送响应回渠道

核心流程：
   入站消息 -> 构建上下文 -> LLM 调用 -> 工具执行 -> 出站消息

主要组件：
- AgentLoop: 主循环类，协调所有组件
- ContextBuilder: 上下文构建
- ToolRegistry: 工具管理
- SessionManager: 会话管理
- SubagentManager: 子代理管理
"""

from nanobot.agent.context import ContextBuilder
from nanobot.agent.tools.registry import ToolRegistry


class AgentLoop:
    """Agent 主循环：核心处理引擎。

    负责协调消息处理、LLM 调用和工具执行的完整流程。

    生命周期：
    1. 初始化：注册默认工具、创建组件
    2. 运行：循环消费消息、处理消息、发送响应
    3. 停止：清理资源

    消息处理流程：
    ```
    入站消息(InboundMessage)
        ↓
    会话获取/创建 (SessionManager)
        ↓
    上下文构建 (ContextBuilder)
        ↓
    LLM 调用 (Provider)
        ↓
    ├─ 无工具调用 → 返回响应
    └─ 有工具调用 → 执行工具 → 循环继续
        ↓
    出站消息(OutboundMessage)
    ```

    Attributes:
        bus: 消息总线，用于接收/发送消息
        provider: LLM 提供商
        workspace: 工作区路径
        model: 使用的模型名称
        max_iterations: 最大迭代次数（防止无限循环）
        context: 上下文构建器
        sessions: 会话管理器
        tools: 工具注册中心
        subagents: 子代理管理器
    """

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 20,
        brave_api_key: str | None = None,
        exec_config: "ExecToolConfig | None" = None,
    ):
        """初始化 AgentLoop。

        Args:
            bus: 消息总线实例，用于消息收发
            provider: LLM 提供商实例（如 LiteLLMProvider）
            workspace: 工作区目录路径
            model: 使用的模型名称（可选，默认使用提供商的默认模型）
            max_iterations: ReAct 循环最大迭代次数，默认 20
            brave_api_key: Brave Search API Key（用于 WebSearchTool）
            exec_config: Shell 执行工具的配置（ExecToolConfig）
        """
        from nanobot.config.schema import ExecToolConfig
        self.bus = bus
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.brave_api_key = brave_api_key
        self.exec_config = exec_config or ExecToolConfig()
        
        # 初始化组件
        self.context = ContextBuilder(workspace)
        self.sessions = SessionManager(workspace)
        self.tools = ToolRegistry()
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            brave_api_key=brave_api_key,
            exec_config=self.exec_config,
        )
        
        self._running = False
        self._register_default_tools()
    
    def _register_default_tools(self) -> None:
        """注册默认工具集。

        注册以下内置工具：
        1. 文件操作工具：
           - ReadFileTool: 读取文件
           - WriteFileTool: 写入文件
           - EditFileTool: 编辑文件
           - ListDirTool: 列出目录

        2. Shell 执行工具：
           - ExecTool: 执行 Shell 命令（受配置限制）

        3. Web 工具：
           - WebSearchTool: 网络搜索
           - WebFetchTool: 获取网页内容

        4. 消息工具：
           - MessageTool: 发送消息到渠道

        5. 子代理工具：
           - SpawnTool: 启动子代理
        """
        # 文件操作工具
        self.tools.register(ReadFileTool())
        self.tools.register(WriteFileTool())
        self.tools.register(EditFileTool())
        self.tools.register(ListDirTool())
        
        # Shell 执行工具
        self.tools.register(ExecTool(
            working_dir=str(self.workspace),
            timeout=self.exec_config.timeout,
            restrict_to_workspace=self.exec_config.restrict_to_workspace,
        ))
        
        # Web 工具
        self.tools.register(WebSearchTool(api_key=self.brave_api_key))
        self.tools.register(WebFetchTool())
        
        # 消息工具
        message_tool = MessageTool(send_callback=self.bus.publish_outbound)
        self.tools.register(message_tool)
        
        # 子代理工具
        spawn_tool = SpawnTool(manager=self.subagents)
        self.tools.register(spawn_tool)
    
    async def run(self) -> None:
        """启动 Agent 主循环。

        工作流程：
        1. 循环运行（直到 stop() 被调用）
        2. 从消息总线消费入站消息（超时 1 秒）
        3. 调用 _process_message 处理消息
        4. 将响应发布到出站队列
        5. 异常时发送错误消息给用户

        此方法应作为异步任务运行（await self.run()）。
        """
        self._running = True
        logger.info("Agent loop started")
        
        while self._running:
            try:
                # 等待下一条消息（超时 1 秒以便检查停止标志）
                msg = await asyncio.wait_for(
                    self.bus.consume_inbound(),
                    timeout=1.0
                )
                
                # 处理消息
                try:
                    response = await self._process_message(msg)
                    if response:
                        await self.bus.publish_outbound(response)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    # 发送错误响应给用户
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content=f"Sorry, I encountered an error: {str(e)}"
                    ))
            except asyncio.TimeoutError:
                # 超时是正常的，继续循环
                continue
    
    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopping")
    
    async def _process_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """处理单条入站消息。

        处理流程：
        1. 系统消息：转发给子代理处理
        2. 普通消息：
           a. 获取/创建会话
           b. 更新工具上下文（MessageTool、 SpawnTool）
           c. 构建消息列表
           d. ReAct 循环：
              - 调用 LLM
              - 如有工具调用：执行工具 → 继续循环
              - 如无工具调用：返回响应
           e. 保存会话历史
           f. 返回出站消息

        Args:
            msg: 入站消息对象，包含 channel、sender_id、chat_id、content、media 等

        Returns:
            出站消息对象，如果无需响应则返回 None
        """
        # 处理系统消息（子代理公告）
        if msg.channel == "system":
            return await self._process_system_message(msg)
        
        logger.info(f"Processing message from {msg.channel}:{msg.sender_id}")
        
        # 获取或创建会话
        session = self.sessions.get_or_create(msg.session_key)
        
        # 更新工具的上下文（设置目标渠道）
        message_tool = self.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool.set_context(msg.channel, msg.chat_id)
        
        spawn_tool = self.tools.get("spawn")
        if isinstance(spawn_tool, SpawnTool):
            spawn_tool.set_context(msg.channel, msg.chat_id)
        
        # 构建消息列表
        messages = self.context.build_messages(
            history=session.get_history(),
            current_message=msg.content,
            media=msg.media if msg.media else None,
        )
        
        # ReAct 循环
        iteration = 0
        final_content = None
        
        while iteration < self.max_iterations:
            iteration += 1
            
            # 调用 LLM
            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model
            )
            
            # 处理工具调用
            if response.has_tool_calls:
                # 添加助手消息（包含工具调用）
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)  # 必须为 JSON 字符串
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts
                )
                
                # 执行工具
                for tool_call in response.tool_calls:
                    args_str = json.dumps(tool_call.arguments)
                    logger.debug(f"Executing tool: {tool_call.name} with arguments: {args_str}")
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
            else:
                # 无工具调用，处理完成
                final_content = response.content
                break
        
        if final_content is None:
            final_content = "I've completed processing but have no response to give."
        
        # 保存会话
        session.add_message("user", msg.content)
        session.add_message("assistant", final_content)
        self.sessions.save(session)
        
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content
        )
    
    async def _process_system_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """处理系统消息（如子代理公告）。

        系统消息的 chat_id 格式为 "original_channel:original_chat_id"，
        用于将响应路由到正确的目标。

        与 _process_message 的区别：
        - 使用原始会话（origin_channel:origin_chat_id）获取上下文
        - 用户消息标记为 "[System: sender_id] content"
        - 响应内容可能更简洁（因为是后台任务）

        Args:
            msg: 系统消息，channel 为 "system"，chat_id 包含原始目标

        Returns:
            出站消息对象
        """
        logger.info(f"Processing system message from {msg.sender_id}")
        
        # 解析原始目标（格式: "channel:chat_id"）
        if ":" in msg.chat_id:
            parts = msg.chat_id.split(":", 1)
            origin_channel = parts[0]
            origin_chat_id = parts[1]
        else:
            # 回退到默认
            origin_channel = "cli"
            origin_chat_id = msg.chat_id
        
        # 使用原始会话获取上下文
        session_key = f"{origin_channel}:{origin_chat_id}"
        session = self.sessions.get_or_create(session_key)
        
        # 更新工具上下文
        message_tool = self.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool.set_context(origin_channel, origin_chat_id)
        
        spawn_tool = self.tools.get("spawn")
        if isinstance(spawn_tool, SpawnTool):
            spawn_tool.set_context(origin_channel, origin_chat_id)
        
        # 构建消息
        messages = self.context.build_messages(
            history=session.get_history(),
            current_message=msg.content
        )
        
        # Agent 循环（简化版）
        iteration = 0
        final_content = None
        
        while iteration < self.max_iterations:
            iteration += 1
            
            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model
            )
            
            if response.has_tool_calls:
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts
                )
                
                for tool_call in response.tool_calls:
                    args_str = json.dumps(tool_call.arguments)
                    logger.debug(f"Executing tool: {tool_call.name} with arguments: {args_str}")
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
            else:
                final_content = response.content
                break
        
        if final_content is None:
            final_content = "Background task completed."
        
        # 保存会话（标记为系统消息）
        session.add_message("user", f"[System: {msg.sender_id}] {msg.content}")
        session.add_message("assistant", final_content)
        self.sessions.save(session)
        
        return OutboundMessage(
            channel=origin_channel,
            chat_id=origin_chat_id,
            content=final_content
        )
    
    async def process_direct(self, content: str, session_key: str = "cli:direct") -> str:
        """直接处理消息（用于 CLI 使用）。

        绕过消息总线，直接调用 _process_message 处理。
        适用于命令行交互场景。

        Args:
            content: 用户输入的消息内容
            session_key: 会话标识符，默认为 "cli:direct"

        Returns:
            Agent 的响应文本
        """
        msg = InboundMessage(
            channel="cli",
            sender_id="user",
            chat_id="direct",
            content=content
        )
        
        response = await self._process_message(msg)
        return response.content if response else ""
