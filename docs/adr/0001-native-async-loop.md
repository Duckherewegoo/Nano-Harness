---
id: 0001-native-async-loop
aliases: []
tags: []
---

# ADR-0001: 放弃图编排框架，使用原生 Async 循环实现 Harness 核心

- Status: Accepted
- Date: 2026-06-22（项目立项与底层设计期）
- Related:
  - 代码：`nano_harness/harness.py`（核心编排引擎）
  - 依赖：`pyproject.toml`（核心依赖仅含 `langchain`，不含 `langgraph`）
  - 背景：本项目与 `task-planner`、`deepdream-agent` 完全独立，但在技术选型上互为对照

## Context

**项目定位**：`nano-harness` 旨在打造一个轻量级、开箱即用的多智能体编排框架，名字里的 "nano" 代表了极致的克制。

**业务痛点**：在多智能体系统（Planner / Executor / Critic / Coordinator）中，核心是一个**反思迭代循环（Reflection Loop）**——规划、执行、评审，如果不达标就带着反馈回到起点重来。

**选型困境**：
在早期的技术选型中，虽然 LangChain 生态已经提供了 `LangGraph` 这样的图状态机框架，但面对多角色的“循环重试”，如果强行套用图编排：
1. 由于环（Cycle）的存在，需要极其复杂的条件边（Conditional Edges）和状态合并逻辑。
2. 作为一个强调“轻量级”的框架，引入图编排会让底层黑盒化，丧失对每一次大模型调用和状态流转的绝对控制。
3. 开发者的核心诉求是“锻炼自己，真实描绘出一个 Harness 的底层运转逻辑”。

## Decision

**不使用 LangGraph 或任何外部的图状态机引擎。**
仅依赖原生的 Python `async/await` 和状态机（`TaskStatus`），手写一个主循环（`while`）来控制四个角色的流转。

核心实现原则（见 `harness.py` 的 `run` 方法）：
- **主循环**：`while task.iteration_count < task.max_iterations`
- **阶段流转**：依次 `await` Planner、Executor、Critic、Coordinator，通过 `TaskStatus` 驱动。
- **反思重试**：Critic 阶段若返回 `needs_revision`，抛出 `continue` 进入下一轮迭代。
- **HITL（人机交互）**：在执行阶段拦截高风险操作，`await` 用户确认。
- **内存克制**：在 `finally` 中坚决执行 `self._tasks.pop(task.task_id, None)`，防止长驻服务发生内存泄漏。

## Alternatives Considered

- **A. 采用 LangGraph 等图编排框架**：否决。
  - 虽然图拓扑在表达静态 DAG 时很直观，但多智能体的“反思闭环”本质上是 `while` 循环，用图去表达会导致条件边急剧膨胀。
  - 违背了 "nano" 的轻量原则，掩盖了底层控制流，不利于学习。
- **B. 纯线性执行（无反思）**：否决。
  - 无法满足 `Critic` 评审不达标后重试的需求，失去了多智能体协作的核心价值。
- **C. 原生 Async 循环 + 状态机**：采纳。
  - 所见即所得，Python 原生逻辑，不需要理解任何框架特有的 DAG 概念，极速轻量。

## Consequences

**正面**
- **极致的轻量与透明**：没有魔法，没有隐藏状态。整个 Agent 调度就像读普通 Python 业务逻辑一样清晰。
- **开发者的底层修炼**：亲手写出 HITL 拦截、反思循环、状态清理，深刻理解 Agent 系统的本质。
- **异常控制的鲁棒性**：得益于原生的 `try...except...finally`，可以精确地在 `finally` 中弹出任务并释放内存。

**负面（接受的代价）**
- **失去自动流式与持久化**：LangGraph 自带的 `checkpointer`（断点恢复）和 `astream`（事件流）需要手写。
  - *缓解措施*：在 `harness.py` 中，任务上下文主要保留在内存 `self._tasks` 中；流式输出依赖外层（FastAPI WebSocket）手动推送日志。代码中注释了“如果外部需要查询历史，应该在此处将 task 持久化到 Redis/DB”。
- **高复杂度拓扑难以扩展**：如果未来业务要从“线性反思循环”演变成“高度分支的树状规划”，手写 `while` 可能会变得难以维护。但在当前的 4 角色闭环中，它是最优解。

**重审条件**
如果未来 `nano-harness` 需要支持“高度自定义的任意 DAG 拓扑”，或者必须原生支持多节点的 checkpoint 回滚，那么单纯的 `while` 循环将不堪重负，届时需要重新考虑引入 LangGraph。

## 备注：框架的“钟摆效应”

在开发者的其他项目中：
- `task-planner` 因长链路 DAG 需要图控制，引入了 LangGraph。
- `deepdream-agent` 因单工具路由，引入了 LangGraph。
- 而本项目作为最早期、最锻炼底子的项目，**反其道而行之，手写原生控制流。**

这不是技术倒退，而是对“何时该用框架，何时该用原生逻辑”的清醒认知。
