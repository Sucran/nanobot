"""Agent 工具模块。

提供 Agent 可用的各种工具：
- Tool: 工具抽象基类
- ToolRegistry: 工具注册中心

内置工具：
- 文件操作: ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
- Shell 执行: ExecTool
- Web 操作: WebSearchTool, WebFetchTool
- 消息发送: MessageTool
- 子代理: SpawnTool
"""
