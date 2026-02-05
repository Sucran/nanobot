# nanobot 项目分析文档

## 项目概述

**nanobot** 是香港大学（HKUDS）开源的轻量级 AI Agent 框架，仅用约 **5,000 行代码** 复刻了 OpenClaw 的核心能力，被称为 "The Ultra-Lightweight Clawdbot"。

| 属性 | 详情 |
|:---|:---|
| **GitHub** | https://github.com/HKUDS/nanobot |
| **定位** | 个人 AI 助手/Agent 框架 |
| **代码量** | ~5,289 行（Python + TypeScript） |
| **特点** | 极致轻量、开源免费、跨平台 |
| **对标** | OpenClaw |

---

## 一、项目整体架构

```
nanobot/
├── nanobot/              # Python 核心逻辑
│   ├── agent/           # Agent 核心（工具、决策）
│   ├── bus/             # 事件总线（消息队列）
│   ├── config/          # 配置管理
│   ├── providers/       # LLM 提供商封装
│   └── utils/           # 工具函数
├── bridge/              # TypeScript 桥接层
│   └── src/             # 消息渠道桥接（WhatsApp/Telegram等）
├── case/                # 使用案例
├── tests/               # 测试
└── workspace/           # 工作空间
```

### 架构特点
- **分层设计**：核心逻辑(Python) + 渠道桥接(TypeScript)
- **事件驱动**：通过事件总线解耦各模块
- **插件化**：工具系统支持动态扩展

---

## 二、核心组件功能说明

### 1. Agent 核心 (`nanobot/agent/`)

| 模块 | 功能 |
|:---|:---|
| `core.py` | Agent 主循环，决策逻辑 |
| `tools/registry.py` | 工具注册中心 |
| `tools/filesystem.py` | 文件系统操作工具 |
| `tools/web.py` | Web 搜索/浏览工具 |

**设计亮点**：
- 支持 ReAct（推理-行动）模式
- 工具自动发现与注册
- 上下文管理

### 2. 事件总线 (`nanobot/bus/`)

| 模块 | 功能 |
|:---|:---|
| `events.py` | 事件定义（Message/Event/Action）|
| `queue.py` | 异步消息队列 |

**作用**：解耦消息接收、处理和响应流程

### 3. LLM 提供商 (`nanobot/providers/`)

| 模块 | 功能 |
|:---|:---|
| `base.py` | 抽象基类 |
| `litellm_provider.py` | 通过 LiteLLM 支持多模型 |

**支持模型**：OpenAI、Anthropic、本地模型等（通过 LiteLLM）

### 4. Bridge 层 (`bridge/src/`)

| 模块 | 功能 |
|:---|:---|
| `index.ts` | 桥接入口 |
| `whatsapp.ts` | WhatsApp 集成 |
| `server.ts` | WebSocket 服务器 |

**职责**：连接各种消息渠道与 Python 核心

---

## 三、代码设计亮点

### 1. 极致轻量
- **5K 行代码** vs OpenClaw 的数万行
- 核心逻辑清晰，易于理解和修改
- 无复杂依赖，部署简单

### 2. 与 OpenClaw 核心对齐
| 特性 | nanobot | OpenClaw |
|:---|:---:|:---:|
| 多渠道消息 | ✅ | ✅ |
| 工具系统 | ✅ | ✅ |
| ReAct 决策 | ✅ | ✅ |
| 本地运行 | ✅ | ✅ |
| 代码量 | ~5K | ~50K+ |

### 3. 事件驱动架构
```python
# 伪代码示例
class EventBus:
    async def emit(self, event: Event):
        # 异步分发事件
        pass
    
    def on(self, event_type: str, handler: Callable):
        # 注册事件处理器
        pass
```

### 4. 配置驱动
- 使用 Pydantic 进行配置校验
- 支持 YAML/JSON 配置文件
- 环境变量覆盖

---

## 四、与 OpenClaw 对比

| 维度 | nanobot | OpenClaw |
|:---|:---|:---|
| **代码量** | ~5K 行 | ~50K+ 行 |
| **定位** | 极简/教育/定制 | 生产级全功能 |
| **学习曲线** | 平缓 | 陡峭 |
| **定制难度** | 容易 | 较难 |
| **功能丰富度** | 核心功能 | 完整生态 |
| **社区** | 新兴 | 成熟 |
| **适用场景** | 个人/轻量/定制 | 企业/生产 |

### 选择建议
- **选 nanobot**：想理解 Agent 原理、轻量定制、学习目的
- **选 OpenClaw**：需要生产级稳定性、丰富功能、企业落地

---

## 五、快速开始

```bash
# 1. 克隆项目
git clone https://github.com/HKUDS/nanobot.git
cd nanobot

# 2. 安装依赖
pip install -e .

# 3. 配置
# 编辑 config.yaml，设置 LLM API Key

# 4. 运行
python -m nanobot
```

---

## 六、总结

**nanobot 是一个优秀的轻量级 Agent 框架**：
- ✅ 代码简洁，易于学习
- ✅ 核心功能完整
- ✅ 可作为 OpenClaw 的简化替代品
- ✅ 适合个人定制和小型项目

**对于主公的 TranscribeProduct 项目**：
- 可参考其事件驱动架构
- 学习其轻量级工具系统设计
- 作为理解 Agent 框架的入门案例

---

*文档生成时间：2026-02-05*
*分析基于 nanobot 最新 main 分支*
