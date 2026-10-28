---
id: 0006-multi-agent-critic
aliases: []
tags: []
---

# ADR-0006: 多角色协作与反思循环的 MVP 设计

- Status: Accepted
- Date: 2026 年 6-9 月（随框架核心同步开发）
- Related:
  - 代码：`nano_harness/agent/`（planner / executor / critic / coordinator）
  - 核心逻辑：`harness.py` 的主循环、`agent/critic.py` 的评审实现
  - 定位：个人学习研究项目，MVP 验证，非商业化生产级

## Context

构建多智能体系统时，业界存在两种极端：
1. **单体 Agent**：只用一个全能 Prompt，遇到复杂任务容易陷入幻觉，且无法自我纠错。
2. **复杂角色扮演（如 MetaGPT）**：定义几十个角色（PM、架构师、开发、测试等），无限套娃，导致 Token 消耗巨大、流程冗长且极易死锁。

本项目的定位是“全面且极具学习价值的轻量级 Demo”。我们希望验证一个核心假设：**Agent 不需要很多角色，只要闭环逻辑对了，就能显著提升产出质量。**

## Decision

**固定采用 4 个核心角色，结合简单的“计划-执行-评审”反思循环，并辅以工程级的兜底防线。**

1. **精简 4 角色模型**：
   - **Planner**（计划）：拆解任务。
   - **Executor**（执行）：调用 Skill / Function Calling 干活。
   - **Critic**（评审）：多维度打分与反馈。
   - **Coordinator**（协调）：汇总结果，转换为用户友好的输出（参考现实任务中的项目经理交付）。
2. **强类型结构化评审（Critic）**：
   - 放弃让 LLM 输出纯文本再用正则去提取，直接使用 LangChain 的 `llm.with_structured_output(CritiqueResult)`。用 Pydantic 约束大模型的输出格式，保证 `needs_revision` 一定是布尔值。
3. **MVP 级工程兜底与熔断**：
   - **异常兜底**：Critic 如果解析崩溃或调用失败，直接通过 `try-except` 返回 `overall_score=70, needs_revision=False`。宁可让任务强行通过，也不让主循环崩溃。
   - **安全门控（熔断机制）**：在 Critic 生成评审后，强制检查 `iteration_count >= max_iterations`。如果是最后一轮，无论大模型觉得多烂，都强制设置 `needs_revision = False`。

## Alternatives Considered

- **A. 引入更多角色（如安全审计员、代码审查员等）**：**否决**。对于通用框架，角色越细分，Prompt 越难写，且在实际运行中 LLM 经常“串戏”。4 个角色是最小完备集。
- **B. 纯文本评审 + 正则提取（Regex）**：**否决**。大模型不听话是常态，一旦它输出 `"needs_revision": "False"`（带引号）或者加个 Markdown 代码块标记，正则就会直接崩溃。结构化输出是唯一正解。
- **C. 构建极其复杂的 DAG 反思图（如 LangGraph）**：**否决**。见 ADR-0001。原生的 `while` 循环足以应对线性重试。

## Consequences

**正面**
- **极简且可控**：没有不可预知的图调度，每一次循环都是由 `while` 和明确的状态机驱动的。
- **抗崩性极强**：即使 LLM 完全胡言乱语，因为 `with_structured_output` 和 `try-except` 的存在，框架依然能返回一个结果，而不是抛出异常挂掉。
- **教学意义满分**：代码非常直观，新手开发者读一遍 `critic.py` 就能明白“如何让大模型输出稳定结构”以及“如何防止 Agent 陷入死循环”。

**负面（接受的代价）**
- **非生产级可靠性**：默认给 70 分的兜底策略，在真实商业场景中会掩盖真实错误。如果在生产级应用中，解析失败应该报警而不是直接放行。
- **局部视野**：`_summarize_results` 只截取了最后 5 步的结果和 300 字符的预览。如果任务极度复杂，Critic 可能会因为看不到全貌而误判。
- **缺乏深度反思**：评审和执行的循环是线性的，没有“回退到某一步骤重新执行”的能力（只能全部重来）。

**备注：关于“Demo 的自我修养”**
这 4 个角色和这套兜底机制，不是为了打造能接管公司的 AI，而是为了证明：**只要有 Planner 负责拆、Executor 负责跑、Critic 负责挑刺、Coordinator 负责收尾，加上合理的容错，一个 MVP 级的 Agent 就能迸发出惊人的完成度。** 至于未来是否会加入多路径回溯或长短期记忆，交给时间去演进。
