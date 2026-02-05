"""LLM 提供商抽象基类模块。

定义 LLM 提供商的统一接口，所有具体实现需继承 LLMProvider：
- ToolCallRequest: LLM 发起的工具调用请求
- LLMResponse: LLM 返回的响应数据
- LLMProvider: 抽象基类，定义必须实现的方法

设计模式：模板方法 + 策略模式
"""
