# NanoHarness

> 轻量级多智能体编排框架 — 驾驭 AI 的工程化实践

NanoHarness 是一个集成了多智能体协作、MCP 协议、Skill 插件、提示词工程与多模态处理的 AI
系统框架。四个角色（Planner / Executor / Critic / Coordinator）通过反思循环驱动工具调用，
迭代至结果达标或达到最大轮次为止。

______________________________________________________________________

## 目录

- [核心特性](#%E6%A0%B8%E5%BF%83%E7%89%B9%E6%80%A7)
- [项目结构](#%E9%A1%B9%E7%9B%AE%E7%BB%93%E6%9E%84)
- [安装](#%E5%AE%89%E8%A3%85)
- [配置](#%E9%85%8D%E7%BD%AE)
- [快速使用](#%E5%BF%AB%E9%80%9F%E4%BD%BF%E7%94%A8)
  - [基础使用](#%E5%9F%BA%E7%A1%80%E4%BD%BF%E7%94%A8)
  - [Skill 注册中心](#skill-%E6%B3%A8%E5%86%8C%E4%B8%AD%E5%BF%83)
  - [提示词优化](#%E6%8F%90%E7%A4%BA%E8%AF%8D%E4%BC%98%E5%8C%96)
  - [MCP 服务端](#mcp-%E6%9C%8D%E5%8A%A1%E7%AB%AF)
  - [MCP 客户端](#mcp-%E5%AE%A2%E6%88%B7%E7%AB%AF)
  - [启动 API 服务](#%E5%90%AF%E5%8A%A8-api-%E6%9C%8D%E5%8A%A1)
- [架构设计](#%E6%9E%B6%E6%9E%84%E8%AE%BE%E8%AE%A1)
  - [Harness 编排流程](#harness-%E7%BC%96%E6%8E%92%E6%B5%81%E7%A8%8B)
  - [反思循环](#%E5%8F%8D%E6%80%9D%E5%BE%AA%E7%8E%AF)
  - [Skill 与 MCP 集成](#skill-%E4%B8%8E-mcp-%E9%9B%86%E6%88%90)
- [Bash 安全机制](#bash-%E5%AE%89%E5%85%A8%E6%9C%BA%E5%88%B6)
- [REST API](#rest-api)
- [开发自定义 Skill](#%E5%BC%80%E5%8F%91%E8%87%AA%E5%AE%9A%E4%B9%89-skill)
- [开发工作流](#%E5%BC%80%E5%8F%91%E5%B7%A5%E4%BD%9C%E6%B5%81)
- [版本历史](#%E7%89%88%E6%9C%AC%E5%8E%86%E5%8F%B2)
- [许可证](#%E8%AE%B8%E5%8F%AF%E8%AF%81)
- [贡献](#%E8%B4%A1%E7%8C%AE)
- [免责声明](#%E5%85%8D%E8%B4%A3%E5%A3%B0%E6%98%8E)

______________________________________________________________________

## 核心特性

### 多智能体协作

| 角色 | 职责 |
| --- | --- |
| **Planner** | 拆解任务、制定执行计划、风险评估 |
| **Executor** | 逐步执行计划、失败重试、上下文传递 |
| **Critic** | 多维度评审打分、给出改进建议、质量把关 |
| **Coordinator** | 结果汇总，以用户友好的形式呈现 |

### Function Calling

- 基于 LangChain 的工具调用机制
- 动态工具加载与注册
- 自动参数解析和验证

### MCP 协议

- **服务端**：将系统能力暴露为 MCP 服务（Tools / Resources / Prompts）
- **客户端**：连接外部 MCP 服务并使用其工具
- **双向转换**：LangChain Tools ↔ MCP 工具互转
- 支持 `stdio` 与 HTTP 两种传输模式

### Skill 插件系统

- 可插拔的技能包架构，提供基类与注册中心
- **内置 Skill**：
  - `BashSkill` — Bash 命令执行（带安全机制）
  - `ImageSkill` — 图片理解与处理
  - `VideoSkill` — 视频分析与处理
  - `AudioSkill` — 音频 / 语音处理
  - `FileSkill` — 文件操作
- 支持自定义 Skill 开发
- 分类管理、标签筛选、关键词搜索

### 提示词工程

- **模板引擎**：多种预设模板（基础 Agent、规划器、执行器、批评家、协调器、思维链、少样本、自我校验等）
- **优化器**：按任务类型自动优化提示词
- 支持少样本学习、思维链、角色扮演等技巧
- 提示词质量分析

### 多模态处理

- **图片**：内容描述、OCR 文字提取、综合分析
- **视频**：信息查询、帧提取、视频摘要、场景检测
- **音频**：语音转文字、特征分析、格式转换、静音检测
- 多后端支持，可优雅降级

### Bash 命令执行（带安全机制）

- 风险等级自动评估（`low` / `medium` / `high` / `forbidden`）
- 高风险命令需用户确认
- 命令黑名单保护
- 工作目录限制，防止路径穿越
- 输出长度限制与超时控制
- 命令历史记录

### REST API + Web 界面

- FastAPI 实现的完整 REST API
- WebSocket 实时流式输出
- 内置 Web 聊天界面
- 自动生成 API 文档

______________________________________________________________________

## 项目结构

```text
nano-harness/
├── nano_harness/
│   ├── __init__.py
│   ├── harness.py                # 核心编排引擎
│   │
│   ├── agent/                    # 多智能体
│   │   ├── __init__.py
│   │   ├── base.py               # BaseAgent 基类
│   │   ├── planner.py            # 规划器
│   │   ├── executor.py           # 执行器
│   │   ├── critic.py             # 批评家
│   │   └── coordinator.py        # 协调器
│   │
│   ├── mcp/                     # MCP 协议
│   │   ├── __init__.py
│   │   ├── server.py             # MCP 服务端
│   │   ├── client.py             # MCP 客户端
│   │   └── tools.py              # 工具适配器
│   │
│   ├── skills/                  # Skill 机制
│   │   ├── __init__.py
│   │   ├── base.py               # BaseSkill 基类
│   │   ├── registry.py           # Skill 注册中心
│   │   └── builtin/              # 内置 Skill
│   │       ├── __init__.py
│   │       ├── bash_skill.py     # Bash 执行
│   │       ├── image_skill.py    # 图片处理
│   │       ├── video_skill.py    # 视频处理
│   │       ├── audio_skill.py    # 音频处理
│   │       └── file_skill.py     # 文件操作
│   │
│   ├── multimodal/              # 多模态处理
│   │   ├── __init__.py
│   │   ├── image.py              # 图像处理
│   │   ├── video.py              # 视频处理
│   │   └── audio.py              # 音频处理
│   │
│   ├── prompts/                 # 提示词工程
│   │   ├── __init__.py
│   │   ├── templates.py          # 模板引擎
│   │   └── optimizer.py          # 提示词优化器
│   │
│   └── api/                     # REST API
│       ├── __init__.py
│       └── server.py             # FastAPI 服务
│
├── web/
│   └── index.html               # Web 界面
├── examples/
│   └── quickstart.py            # 快速上手示例
├── config.yaml                  # 配置文件
├── pyproject.toml               # 构建与依赖声明
├── requirements.txt             # 依赖清单（由 pyproject.toml 生成）
├── main.py                     # 入口文件
└── README.md
```


______________________________________________________________________

## 安装

### 环境要求

| 项目 | 要求 |
| --- | --- |
| Python | `>=3.10`（3.10 / 3.11 / 3.12 已声明支持） |
| 操作系统 | Linux / macOS / Windows |
| 外部依赖 | `pytesseract` 需要系统安装 Tesseract OCR；`opencv-python` 需要系统图像库 |

### 从源码安装

```bash
git clone https://github.com/DakeGinger/nano-harness.git
cd nano-harness

# 核心依赖
pip install -e .

# 开发依赖（格式化、静态检查、测试）
pip install -e ".[dev]"
```

`pyproject.toml` 声明的运行时依赖：

| 分类 | 依赖 |
| --- | --- |
| 核心框架 | `langchain>=0.2.0`、`langchain-core>=0.2.0`、`langchain-community>=0.2.0` |
| API 服务 | `fastapi>=0.110.0`、`uvicorn>=0.29.0`、`pydantic>=2.6.0` |
| 图片 | `Pillow>=10.0.0`、`pytesseract>=0.3.10` |
| 视频 | `opencv-python>=4.9.0` |
| 音频 | `pydub>=0.25.1`、`SpeechRecognition>=3.10.0` |
| 工具库 | `PyYAML>=6.0`、`python-dotenv>=1.0.0`、`requests>=2.31.0` |

> 若你使用的是 `requirements.txt` 而非 `pyproject.toml`，请保持其内容与上表一致，
> 避免两份清单出现分歧。

### 快速开始

```bash
# 1. 克隆项目
git clone https://github.com/DakeGinger/nano-harness.git
cd nano-harness

# 2. 安装依赖
pip install -e .

# 3. 配置 LLM（可选，不配置也能运行演示模式）
#    编辑 config.yaml，填入你的 API Key

# 4. 启动服务
python main.py

# 5. 访问 Web 界面
#    打开浏览器访问 http://localhost:8000/ui
```

### 运行示例

```bash
# 运行快速上手示例
python examples/quickstart.py

# 演示模式
python main.py --demo

# 命令行交互
python main.py --cli
```

### 安装后的 CLI 入口

`pyproject.toml` 通过 `[project.scripts]` 声明了可执行入口：

```bash
# 等价于 python -m main 或 python main.py，具体行为取决于 main.py 的 main()
nano-harness
```

若该命令未生效，请先确认已执行 `pip install -e .`，并检查当前虚拟环境是否在 `PATH` 中。

______________________________________________________________________

## 配置

编辑 `config.yaml` 配置系统参数：

```yaml
# LLM 配置
llm:
  provider: "openai"
  model: "gpt-4o-mini"
  api_key: "your-api-key"
  base_url: ""
  temperature: 0.7

# Harness 配置
harness:
  max_iterations: 3
  confidence_threshold: 0.7
  enable_reflection: true
  enable_user_confirm: true

# Skill 配置
skills:
  auto_load_builtin: true
  work_dir: "./workspace"
  bash:
    enabled: true
    timeout: 30
    auto_confirm_low_risk: true

# API 配置
api:
  host: "0.0.0.0"
  port: 8000
```

> 敏感字段（如 `llm.api_key`）建议通过环境变量注入，避免明文写入配置文件并提交到仓库。

______________________________________________________________________

## 快速使用

### 基础使用

```python
from nano_harness import Harness, HarnessConfig

# 创建配置
config = HarnessConfig(
    max_iterations=3,
    confidence_threshold=0.7,
    enable_reflection=True,
    enable_user_confirm=True,
)

# 创建 Harness 实例
harness = Harness(config=config)

# 注册 Skill
from nano_harness.skills.builtin import BashSkill, FileSkill

harness.register_skill(BashSkill(work_dir="./workspace"))
harness.register_skill(FileSkill(work_dir="./workspace"))

# 设置用户确认回调
def on_user_confirm(command: str, risk_level: str) -> bool:
    """用户确认回调"""
    print(f"⚠️  高风险命令（{risk_level}）：{command}")
    answer = input("是否执行？(y/n): ")
    return answer.lower() == "y"

harness.set_user_confirm_callback(on_user_confirm)

# 运行任务
result = harness.run("帮我分析当前目录下的文件")
print(result["final_output"])
```

### Skill 注册中心

```python
from nano_harness.skills import SkillRegistry
from nano_harness.skills.builtin import BashSkill, ImageSkill

# 创建注册中心
registry = SkillRegistry()

# 注册 Skill
registry.register(BashSkill())
registry.register(ImageSkill())

# 获取所有工具
tools = registry.get_all_tools()
print(f"共 {len(tools)} 个工具")

# 搜索 Skill
results = registry.search_skills("image")
for skill in results:
    print(f"- {skill.name}: {skill.description}")
```

### 提示词优化

```python
from nano_harness.prompts import PromptOptimizer

optimizer = PromptOptimizer()

# 优化提示词
optimized = optimizer.optimize(
    "写一个Python脚本",
    task_type="coding",
    add_cot=True,
    add_self_check=True,
)

print(optimized)

# 分析提示词质量
analysis = optimizer.analyze_prompt(optimized)
print(f"清晰度评分: {analysis['clarity_score']}/100")
```

### MCP 服务端

```python
from nano_harness.mcp.server import MCPServer

# 创建 MCP 服务端
server = MCPServer(name="my-tools", version="1.0.0")

# 注册工具
def add(a: int, b: int) -> int:
    """两个数相加"""
    return a + b

server.register_tool(
    name="add",
    description="两个数相加",
    handler=add,
    input_schema={
        "type": "object",
        "properties": {
            "a": {"type": "integer", "description": "第一个数"},
            "b": {"type": "integer", "description": "第二个数"},
        },
        "required": ["a", "b"],
    },
)

# 以 stdio 模式运行
server.run_stdio()
```

### MCP 客户端

```python
from nano_harness.mcp.client import MCPClient

# 连接 MCP 服务
client = MCPClient()
client.connect_stdio(["python", "my_mcp_server.py"])

# 列出工具
tools = client.list_tools()
for tool in tools:
    print(f"- {tool['name']}: {tool['description']}")

# 调用工具
result = client.call_tool("add", {"a": 1, "b": 2})
print(f"结果: {result}")

# 转换为 LangChain 工具
langchain_tools = client.get_langchain_tools()
```

### 启动 API 服务

```python
from nano_harness.api import run_server

# 启动服务
run_server(host="0.0.0.0", port=8000)
```

或直接运行：

```bash
python main.py --port 8000
```

______________________________________________________________________

## 架构设计

### Harness 编排流程

```text
用户输入
    │
    ▼
┌─────────────┐
│   Planner   │  规划器：拆解任务，制定计划
└──────┬──────┘
       ▼
┌─────────────┐
│  Executor   │  执行器：逐步执行，调用工具
└──────┬──────┘
       ▼
┌─────────────┐
│   Critic    │  批评家：评审结果，质量把关
└──────┬──────┘
       ▼
     达标？ ──否──▶ 迭代（最多 N 轮）
       │
      是
       ▼
┌─────────────┐
│ Coordinator │  协调器：汇总结果，用户友好
└──────┬──────┘
       ▼
  最终输出
```

### 反思循环

系统支持反思迭代机制：

1. 规划 → 执行 → 评审
1. 若评分不达标，根据批评家的建议重新执行
1. 最多迭代 N 轮（由 `harness.max_iterations` 配置）
1. 确保输出质量

### Skill 与 MCP 集成

```text
┌─────────────┐       ┌─────────────┐
│    Skill    │──────▶│  MCP Server │  暴露为 MCP 服务
└─────────────┘       └─────────────┘
       ▲
       │  双向转换
       ▼
┌─────────────┐       ┌─────────────┐
│ LangChain   │◀──────│  MCP Client │  接入外部 MCP
│    Tools    │       └─────────────┘
└─────────────┘
```

______________________________________________________________________

## Bash 安全机制

系统内置多层安全保护：

1. **风险等级评估**：自动判断命令危险程度
   - `low`：只读操作（`ls`、`cat`、`pwd` 等）
   - `medium`：写操作（`mkdir`、`cp`、`mv` 等）
   - `high`：高风险操作（删除、系统修改等）
   - `forbidden`：绝对禁止（`rm -rf /`、`mkfs` 等）
1. **用户确认**：高风险命令必须经过用户确认
1. **命令黑名单**：极度危险的命令直接拒绝执行
1. **工作目录限制**：防止路径穿越攻击
1. **输出限制**：防止输出过大导致内存问题
1. **超时控制**：防止命令卡死

______________________________________________________________________

## REST API

启动服务后访问：

- **Swagger UI**：http://localhost:8000/docs
- **ReDoc**：http://localhost:8000/redoc
- **Web 界面**：http://localhost:8000/ui

### 主要接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/chat` | 对话接口 |
| WS | `/ws/chat` | WebSocket 实时对话 |
| POST | `/api/v1/tasks` | 创建任务 |
| GET | `/api/v1/tasks/{id}` | 查询任务状态 |
| GET | `/api/v1/skills` | 列出所有 Skill |
| GET | `/api/v1/mcp/tools` | 列出 MCP 工具 |
| POST | `/api/v1/mcp/call` | 调用 MCP 工具 |

______________________________________________________________________

## 开发自定义 Skill

```python
from nano_harness.skills import BaseSkill
from langchain.tools import tool

class MySkill(BaseSkill):
    """我的自定义 Skill"""

    def __init__(self):
        super().__init__(
            name="my_skill",
            description="我的自定义技能包",
            version="1.0.0",
            author="your-name",
            category="utility",
            tags=["custom", "demo"],
        )

    def initialize(self, context=None):
        """初始化钩子"""
        print("MySkill 初始化完成")

    def get_tools(self):
        """返回工具列表"""

        @tool
        def my_tool(query: str) -> str:
            """我的自定义工具

            Args:
                query: 输入查询
            """
            return f"处理结果: {query}"

        return [my_tool]

    def cleanup(self):
        """清理钩子"""
        print("MySkill 清理完成")
```

______________________________________________________________________

## 开发工作流

代码风格与静态检查由 `pyproject.toml` 中的 `[tool.ruff]` 统一约束：

| 工具 | 配置来源 | 说明 |
| --- | --- | --- |
| `ruff`（lint + format） | `[tool.ruff]` | `line-length = 100`，`target-version = "py310"` |
| `pytest` | `[tool.pytest.ini_options]` | `testpaths = ["tests"]`，默认参数 `-q` |

```bash
# 格式化
ruff format src/ tests/

# 静态检查
ruff check src/ tests/

# 运行测试
pytest
```

`pyproject.toml` 中已忽略 `E501`（行长度交由格式化工具处理）与若干 FastAPI / 中文注释相关的
规则；若你调整了忽略列表，请同步更新此处说明。

______________________________________________________________________

## 版本历史

### v1.0.0

- 核心 Harness 编排引擎
- 4 角色多智能体（规划 / 执行 / 评审 / 协调）
- Function Calling 支持
- MCP 协议（服务端 + 客户端 + 适配器）
- Skill 插件系统（基类 + 注册中心）
- 5 个内置 Skill（Bash / Image / Video / Audio / File）
- 提示词工程（模板引擎 + 优化器）
- 多模态处理（图片 / 视频 / 音频）
- Bash 安全执行机制
- REST API + WebSocket
- Web 聊天界面
- 配置文件支持

______________________________________________________________________

## 许可证

本项目以 **GPL-3.0-or-later** 发布（见 `pyproject.toml` 的 `license` 字段与
`classifiers`）。

- 源码文件顶部须保留原有版权与许可证声明
- 修改文件应标注变更
- 分发时须提供许可证副本
- 本项目不提供任何明示或暗示的担保

## 贡献

欢迎提交 Issue 和 Pull Request。提交前请确认：

- `pytest` 通过
- `ruff check` 与 `ruff format` 无新增警告
- 新增功能附带对应测试

## 免责声明

本项目仅供学习和研究使用。使用 Bash 命令执行功能时请注意安全：高风险操作会触发用户确认，
但仍需谨慎使用，避免在共享或生产环境中开放不受信任的命令执行权限。
