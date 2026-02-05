"""LLM 提供商抽象模块。

提供统一的 LLM 接口，支持多种模型提供商：
- LLMProvider: 抽象基类，定义提供商接口
- LLMResponse: LLM 响应数据结构
- LiteLLMProvider: 基于 LiteLLM 的多提供商实现

支持的提供商：OpenAI, Anthropic, Gemini, OpenRouter, vLLM, 智谱等
"""
