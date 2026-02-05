"""工具注册中心模块。

提供动态工具管理功能：
- 注册/注销工具
- 获取工具定义（OpenAI 格式）
- 执行工具调用

工具以名称为键存储，支持：
- 同步验证参数
- 异步执行
- 错误处理
"""
    
    def register(self, tool: Tool) -> None:
        """注册工具。

        Args:
            tool: 工具实例，必须继承 Tool 基类
        """
        self._tools[tool.name] = tool
    
    def unregister(self, name: str) -> None:
        """注销工具（按名称）。

        Args:
            name: 要注销的工具名称
        """
        self._tools.pop(name, None)
    
    def get(self, name: str) -> Tool | None:
        """获取工具实例（按名称）。

        Args:
            name: 工具名称

        Returns:
            工具实例，如果不存在则返回 None
        """
        return self._tools.get(name)
    
    def has(self, name: str) -> bool:
        """检查工具是否已注册。

        Args:
            name: 工具名称

        Returns:
            True 如果工具已注册，False 否则
        """
        return name in self._tools
    
    def get_definitions(self) -> list[dict[str, Any]]:
        """获取所有工具定义（OpenAI 格式）。

        用于 LLM 的 tool_calls 功能，每个工具定义包含：
        - type: "function"
        - function: 包含 name、description、parameters

        Returns:
            工具定义列表，可直接传给 LLM
        """
        return [tool.to_schema() for tool in self._tools.values()]
    
    async def execute(self, name: str, params: dict[str, Any]) -> str:
        """执行工具调用。

        执行流程：
        1. 根据名称查找工具
        2. 验证参数
        3. 执行工具（异步）
        4. 捕获并返回错误

        Args:
            name: 要执行的工具名称
            params: 工具参数字典

        Returns:
            工具执行结果字符串
            错误时返回格式化的错误信息
        """
        tool = self._tools.get(name)
        if not tool:
            return f"Error: Tool '{name}' not found"

        try:
            # 参数验证
            errors = tool.validate_params(params)
            if errors:
                return f"Error: Invalid parameters for tool '{name}': " + "; ".join(errors)
            # 执行工具
            return await tool.execute(**params)
        except Exception as e:
            return f"Error executing {name}: {str(e)}"
    
    @property
    def tool_names(self) -> list[str]:
        """Get list of registered tool names."""
        return list(self._tools.keys())
    
    def __len__(self) -> int:
        return len(self._tools)
    
    def __contains__(self, name: str) -> bool:
        return name in self._tools
