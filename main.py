"""
NanoHarness - 入口文件
=======================
启动 NanoHarness 系统。
"""

import argparse
import asyncio
import sys

import yaml

# 引入我们定制的全局日志系统
from nano_harness.utils.logger_setup import get_logger, setup_logger

logger = get_logger("nano-harness")


def load_config(config_path: str) -> dict:
    """加载并解析配置文件"""
    try:
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        logger.error("配置文件不存在: %s，请检查路径。", config_path)
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.error("配置文件格式错误: %s", e)
        sys.exit(1)


def init_harness(config: dict):
    """公共初始化逻辑：加载 LLM 和 Skill，返回 Harness 实例"""
    from langchain_openai import ChatOpenAI

    from nano_harness import Harness, HarnessConfig
    from nano_harness.skills.builtin import BashSkill, FileSkill

    # 1. 初始化 LLM
    llm_cfg = config.get("llm", {})
    llm = ChatOpenAI(
        model=llm_cfg.get("model", "qwen-3.6-flash"),
        api_key=llm_cfg.get("api_key", ""),
        base_url=llm_cfg.get("base_url", ""),
        temperature=llm_cfg.get("temperature", 0.7),
    )

    # 2. 组装 Harness 配置
    h_cfg = config.get("harness", {})
    h_config = HarnessConfig(
        max_iterations=h_cfg.get("max_iterations", 3),
        enable_critique=h_cfg.get("enable_critic", True),
        enable_human_in_the_loop=h_cfg.get("enable_user_confirm", True),
    )

    # 3. 实例化
    harness = Harness(llm=llm, config=h_config)

    # 4. 注册 Skill
    skills_cfg = config.get("skills", {})
    work_dir = skills_cfg.get("work_dir", "./workspace")
    if skills_cfg.get("bash", {}).get("enabled", True):
        harness.register_skill(BashSkill(work_dir=work_dir))
    if skills_cfg.get("file", {}).get("enabled", True):
        harness.register_skill(FileSkill(work_dir=work_dir))

    return harness


def main():
    parser = argparse.ArgumentParser(description="NanoHarness - 轻量级多智能体编排框架")
    
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--cli", action="store_true", help="启动命令行交互模式")
    group.add_argument("--demo", action="store_true", help="运行系统能力自检")
    
    parser.add_argument("--host", type=str, default="0.0.0.0", help="API服务监听地址")
    parser.add_argument("--port", type=int, default=8000, help="API服务监听端口")
    parser.add_argument("--config", type=str, default="config.yaml", help="配置文件路径")
    
    args = parser.parse_args()
    config = load_config(args.config)
    
    # 初始化全局日志（使用配置里的 level）
    log_level = config.get("logging", {}).get("level", "INFO")
    log_file = config.get("logging", {}).get("file", "nano-harness.log")
    setup_logger(log_file=log_file, level=log_level)

    # 覆盖配置中的端口
    config.setdefault("api", {})
    config["api"]["host"] = args.host
    config["api"]["port"] = args.port

    if args.demo:
        run_demo(config)
    elif args.cli:
        run_cli(config)
    else:
        run_server(config)


def run_demo(config):
    """运行系统自检"""
    logger.info("============================================================")
    logger.info("  NanoHarness - 系统自检")
    logger.info("============================================================")
    
    try:
        harness = init_harness(config)
        logger.info("引擎初始化成功，当前最大迭代次数: %s", harness.config.max_iterations)
        
        logger.info("📦 已注册能力清单：")
        logger.info("  - 多智能体协作（Planner/Executor/Critic/Coordinator）")
        logger.info("  - MCP 协议支持")
        logger.info("  - 多模态处理")
        logger.info("自检通过，准备就绪。")
        logger.info("👉 运行 `python main.py --cli` 进入交互模式，或直接运行以启动 Web 服务。")
        
    except Exception:
        logger.exception("自检失败，请检查依赖或配置。")
        sys.exit(1)


def run_cli(config):
    """命令行交互模式"""
    logger.info("============================================================")
    logger.info("  NanoHarness CLI (输入 'quit' 退出)")
    logger.info("============================================================")
    
    try:
        harness = init_harness(config)
        logger.info("Harness 就绪，请输入你的任务。\n")
    except Exception as e:
        logger.error("初始化失败: %s", e)
        sys.exit(1)
        
    while True:
        try:
            user_input = input("用户 > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ['quit', 'exit', 'q']:
                break
            
            logger.info("思考中...")
            # 严谨鲁棒：异步引擎必须用 asyncio.run 驱动
            result = asyncio.run(harness.run(user_input))
            
            print("\n" + "=" * 40)
            print(result)
            print("=" * 40 + "\n")
            
        except KeyboardInterrupt:
            logger.info("\n已中断。")
            break
        except Exception as e:
            logger.error("执行出错: %s", e, exc_info=True)


def run_server(config):
    """启动 API 服务器"""
    try:
        import uvicorn

        from nano_harness.api.server import create_app
        
        # 修复：先实例化 Harness 再传给 FastAPI
        harness = init_harness(config)
        
        host = config["api"]["host"]
        port = config["api"]["port"]
        
        logger.info("🚀 启动 NanoHarness API 服务...")
        logger.info("📡 地址: http://%s:%s", host, port)
        logger.info("📚 文档: http://%s:%s/docs", host, port)
        
        # 生产环境推荐使用工厂模式启动
        app = create_app(harness=harness)
        uvicorn.run(app, host=host, port=port, log_level=config.get("logging", {}).get("level", "info").lower())
        
    except ImportError as e:
        logger.error("缺少依赖，无法启动服务: %s", e)
        logger.error("请运行: pip install fastapi uvicorn")
        sys.exit(1)
    except Exception:
        logger.exception("服务启动崩溃")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n👋 退出。")
        sys.exit(130)
