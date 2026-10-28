---
id: 0005-manual-mcp-impl
aliases: []
tags: []
---

# ADR-0005: 手动实现 MCP 协议及双向桥接

- Status: Accepted
- Date: 2026 年 6-9 月（随框架核心同步开发）
- Related:
  - 代码：`nano_harness/mcp/client.py`、`server.py`、`tools.py`
  - 生态：Anthropic 提出的 Model Context Protocol (MCP)
  - 定位：纯手写实现，未依赖官方 pip 包，用于底层研究

## Context

在构思 `nano-harness` 的架构时，开发者的目标是打造一个“大而全”的 Agent 学习范本（`Agent = LLM + Harness`）。此时恰逢 Anthropic 推出 MCP（Model Context Protocol）协议，旨在标准化大模型与外部工具的交互。

**面临的考量**：
1. **生态前瞻性**：未来的 Agent 不应该是孤岛，它需要能连接各种外部的 MCP 服务（比如 Claude Desktop、各种 MCP Server），也需要能把自己的能力暴露给别的 MCP 客户端。
2. **学习价值**：如果直接 `pip install mcp` 并调用，就失去了研究协议底层运作机制的机会。为了彻底搞懂 MCP 的 JSON-RPC 通信、stdio/http 传输方式，以及它与现有工具标准的差异，从头手写一遍是最好的学习方式。

## Decision

**在框架内手动实现 MCP 协议的核心模块，并实现与 LangChain Tool 的双向互转。**

1. **MCP Server**：将 `nano-harness` 内的 Skill 注册为 MCP Tools/Resources/Prompts，支持 `stdio` 模式运行。
2. **MCP Client**：允许框架连接外部的 MCP Server，获取外部工具列表并执行调用。
3. **双向适配器（Adapter）**：在 `tools.py` 中实现 `LangChain Tool` ↔ `MCP Tool` 的 Schema 互转与调用封装。

## Alternatives Considered

- **A. 直接使用官方 `mcp` Python SDK**：**否决**。虽然能快速实现，但封装较重，且不符合本项目“极简、手搓、学习研究”的初衷。
- **B. 不集成 MCP，只用自己的 Skill 机制**：**否决**。会导致框架成为封闭生态，无法与日益庞大的 MCP 开源工具库互通。
- **C. 选择其他 RPC 协议（如 gRPC / OpenAPI）**：**未采纳**。MCP 专为 LLM 设计（包含 Tool 参数 Schema 等），原生契合 Agent 场景。

## Consequences

**正面**
- **极高的研究价值**：框架具备了真正的“教科书”级别水准。开发者可以顺着 `mcp/client.py` 完整看懂 JSON-RPC 的报文长什么样，工具是如何被调用的。
- **生态破壁**：用户的 Agent 可以瞬间拥有成千上万个外部 MCP 插件的能力，也可将自己写的 Skill 暴露给其他 Agent 框架。
- **极致轻量**：手写的协议模块只包含了框架必需的核心逻辑，无需引入庞大的底层传输依赖。

**负面（接受的代价）**
- **兼容性挑战**：手写的实现如果遇到未来 MCP 协议的版本更新（或者特殊边界情况），可能需要自行维护和打补丁。
- **传输层复杂度**：`stdio` 模式涉及进程间通信与异步流的处理，维护成本比单纯的网络请求高；HTTP 模式也需要处理长连接。
- **调试难度**：协议解析失败时，错误信息容易被掩盖在异步 IO 中，排查不如普通的 API 调用直观。

**备注**
在 `nano_harness/mcp/` 下的三个文件（`client.py`、`server.py`、`tools.py`），构成了这个项目最硬核的底层技术资产。它证明了在轻量级框架中实现标准工业协议是完全可行的。
