---
id: 0003-optional-dependencies
aliases: []
tags: []
---

# ADR-0003: 可选依赖隔离与 Extras 设计

- Status: Accepted
- Date: 2026-10-19（commit `b405a64`：更新可选依赖和版本号）
- Related:
  - 配置：`pyproject.toml`（`[project.optional-dependencies]` 声明）
  - 文档：`README.md`（安装说明与各模态依赖表）
  - 对比案例：`deepdream-agent`（将 PyTorch 塞进主依赖的沉重教训）

## Context

`nano-harness` 作为一个全能型 Agent 框架，内置了 5 个核心 Skill：
`BashSkill`、`FileSkill`、`ImageSkill`、`VideoSkill`、`AudioSkill`。

**痛点在于**：
1. **依赖爆炸**：处理图片需要 `Pillow` 和 `pytesseract`，处理视频需要 `opencv-python`，处理音频需要 `pydub`。如果把所有依赖都放进 `dependencies`，一个只想用 Bash 和文本对话的开发者，被迫要安装上百 MB 的多媒体库。
2. **系统级编译灾难**：`opencv-python` 和 `pytesseract` 在不同操作系统（尤其是 Windows 和精简版 Linux）上安装时，极易因为缺少系统级 C++ 库或 OCR 引擎而直接报错。
3. **与“Nano”理念背离**：项目的名字叫 `nano-harness`，核心卖点是轻量。如果安装包比 LangChain 还重，那就违背了立项的初衷。

## Decision

采取**依赖隔离（Extras）**策略。`pyproject.toml` 中的依赖分为三类：

1. **核心依赖（Core）**：只包含运行基础 Agent 和 API 服务的必备库（`langchain`、`fastapi`、`uvicorn`、`pydantic`）。
2. **可选依赖（Extras）**：按模态切分成组——
   - `vision`：Pillow, pytesseract
   - `video`：opencv-python
   - `audio`：pydub, SpeechRecognition
   - `fast-text`：pyahocorasick（高性能匹配，可有可无）
3. **一键全量（Full）**：提供 `nano-harness[full]` 的聚合标识，方便需要全功能的用户一键安装。

**配套代码约束**：所有处理多模态的代码，必须在**函数内部按需导入**（Lazy Import），且必须使用 `try...except ImportError` 进行优雅降级（抛出自定义的友好报错，而不是直接让程序崩溃）。

## Alternatives Considered

- **A. 全量依赖（All-in-one）**：把所有库写进 `dependencies`。否决。这是早期项目（如 `deepdream-agent`）常犯的错误，导致安装门槛极高，违背轻量初衷。
- **B. 极简主义（纯文本 & Bash）**：只保留文本能力，砍掉多媒体 Skill。否决。这阉割了框架的多模态潜力，不符合“全能 Agent”的定位。
- **C. 拆分多个独立的包（如 `nano-harness-vision`、`nano-harness-video`）**：否决。对于个人维护的开源框架来说，多包发布、版本同步和交叉依赖的维护成本太高（Monorepo 的痛点）。
- **D. Extras 隔离（采纳）**：兼顾轻量与扩展，是 Python 生态（如 `pandas[performance]`）的标准最佳实践。

## Consequences

**正面**

- **极速体验**：基础安装（`pip install -e .`）几乎只需要几秒钟，只拉起最小可运行环境。
- **规避系统级崩溃**：用户如果不需要处理视频，完全不用管 `opencv` 的系统依赖报错。
- **清晰的边界**：用户能直观知道自己装了什么，用了什么。

**负面（接受的代价）**

- **用户容易“漏装”**：新手用户很可能直接 `pip install nano-harness`，然后在调用 `ImageSkill` 时遇到 `ImportError`。
  - *缓解措施*：在代码层拦截 `ImportError`，并在报错中提示用户执行 `pip install nano-harness[vision]`。
- **测试矩阵膨胀**：CI 最好需要覆盖“只装核心”和“装全量”两种情况，防止在无多模态库的环境下出现 `NameError`。
- **依赖冲突风险**：如果用户自己项目里的 `opencv` 版本和框架 Extras 里的版本冲突，pip 解析器可能会卡住。

**备注：向“重依赖”的决裂**

在 `deepdream-agent` 项目中，由于核心功能就是跑 PyTorch，把 `torch` 放进主依赖是合理的。
但在 `nano-harness` 中，Agent 编排才是核心，多模态只是外设。这种 **“主框架 + 外挂驱动”** 的设计，让框架真正达到了“Nano”的体量。
