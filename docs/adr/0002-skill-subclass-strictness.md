---
id: 0002-skill-subclass-strictness
aliases: []
tags: []
---

# ADR-0002: 基于 `__init_subclass__` 的 Skill 强类型约束与懒加载机制

- Status: Accepted
- Date: 2026-10-19（commit `b151cf1`：增强 skill 表现与安全鲁棒性）
- Related:
  - 代码：`nano_harness/skills/base.py`、`nano_harness/skills/registry.py`
  - 依赖：核心依赖不含 `opencv-python`、`Pillow` 等重型库，全在 `optional-dependencies`

## Context

`nano-harness` 的核心扩展能力依赖于 **Skill 插件系统**。用户或第三方可以编写自定义的 Skill 挂载进框架。这带来了三个工程挑战：

1. **契约容易断裂**：如果开发者写了一个 `MySkill`，但不小心漏了 `name` 或 `description`，系统直到真正实例化、甚至路由到它时才会报错（`AttributeError`），这极难排查。
2. **重依赖导致启动灾难**：框架内置了 `ImageSkill`、`VideoSkill` 等，它们依赖 `OpenCV`、`Pillow` 等重型包。如果一个纯文本用户没有安装视频处理包，却因为 `import` 语句把整个项目拖垮（`ImportError`），体验极差。
3. **元数据查询的性能黑洞**：系统需要一个“注册中心”展示所有可用 Skill 的列表，如果每次查询都去调用 `get_tools()` 来统计工具数量（而 `get_tools()` 内部可能需要实例化重型对象），会导致严重的卡顿。

## Decision

在基类 `BaseSkill` 层面实施**元编程防呆**与**状态隔离**，并在系统层面实施**按需导入**：

1. **`__init_subclass__` 强校验（Fail Fast）**：利用 Python 魔法方法，在任何子类被定义（`import`）的瞬间，强制检查 `name` 和 `description` 是否非空。未定义则直接抛出 `ValueError`，将错误扼杀在模块加载期。
2. **状态隔离**：坚决不在类属性上使用 `list`（如 `tags = []`），而是放到 `__init__` 中实例化，彻底杜绝 Python 经典的“跨实例共享可变默认值” Bug。
3. **元数据懒加载与缓存**：在 `get_metadata` 中，将 `tool_count` 的计算结果缓存到实例的 `_cached_tool_count` 中；并在 `cleanup` 时销毁缓存。
4. **抑制 import 副作用**：只有在真正要执行某个 Skill 的逻辑时，才在函数内部进行 `import`，或者通过注册中心按需加载，确保没装某依赖的用户不会看到报错。

## Alternatives Considered

- **A. 依赖文档和人工约定**：最原始的方案，不仅不可靠，而且对开源框架的贡献者极其不友好。
- **B. 在 `__init__` 时进行校验**：能用，但如果用户的代码只是被 `import` 准备注册，还没实例化，报错依然会延迟。`__init_subclass__` 是真正的“定义即校验”。
- **C. 每次查元数据都跑一遍 `get_tools()`**：如果不做缓存，UI 端每次刷新列表，都会导致服务器 CPU 飙升。
- **D. 把重依赖全部塞进 `pyproject.toml` 的主依赖**：这与 "nano" 理念背道而驰（对比 `deepdream-agent` 把 PyTorch 放进主依赖的沉重）。

## Consequences

**正面**

- **史诗级防呆**：开发者只要写出 `class MySkill(BaseSkill):`，如果忘了写 `name`，IDE 或终端在 `import` 时就会立刻标红或报错。这极大降低了“插件不生效”的沟通成本。
- **性能极致可控**：UI 端拉取 Skill 列表时，响应时间从 O(N) 降到了 O(1)（得益于缓存）。
- **启动极快**：通过惰性加载，即使用户没装 OpenCV，系统也能完美启动并运行纯文本任务。
- **安全兜底**：`get_metadata` 中包了 `try-except`，即使子类 `get_tools` 内部爆炸，元数据接口也只会返回 `0`，绝不拖垮整个服务。

**负面（接受的代价）**

- **理解成本增加**：`__init_subclass__` 属于 Python 的隐式魔法。对于初学者来说，必须理解“类定义时会自动触发基类方法”这一机制，否则会感到困惑。
- **调试断点失效**：因为有隐式校验，某些传统的 Debug 模式可能抓不到抛出异常的调用栈起点，只能靠异常信息里的 `cls.__name__` 定位。

**备注：向“懒加载”妥协的工程平衡**

在 commit `b151cf1` 中，同时引入了“按需加载”与“`__init_subclass__`”双重机制。
通常来说，“强校验”和“懒加载”是冲突的：如果不 import，怎么校验？
答案是：**类定义（class definition）通过静态分析或轻量级的注册表登记实现强校验；而实例化（instantiation）通过延迟导入重型包实现懒加载。**
这一设计完美兼顾了“早报错（Fail Fast）”与“低开销（Lazy）”。
