import contextvars
import logging
import sys

# 使用 ContextVar 保证异步并发安全
_req_id_var = contextvars.ContextVar("req_id", default="system")

def set_req_id(req_id: str):
    """设置当前上下文的 Request ID (供 FastAPI 中间件调用)"""
    _req_id_var.set(req_id)

def get_req_id() -> str:
    """获取当前上下文的 Request ID"""
    return _req_id_var.get()

class ReqIdFilter(logging.Filter):
    """注入 Request ID 到日志记录的过滤器"""
    def filter(self, record):
        record.req_id = _req_id_var.get()
        return True

def setup_logger(log_file: str = "nano-harness.log", level: str = "INFO"):
    """
    全局初始化日志（仅在 main.py 启动时调用一次）
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # 避免重复添加 Handler（例如在测试中被多次调用）
    if root_logger.handlers:
        return

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | [%(req_id)s] | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    req_id_filter = ReqIdFilter()

    # 1. 控制台输出 (输出到 stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(req_id_filter)
    root_logger.addHandler(console_handler)

    # 2. 文件输出 (持久化)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.addFilter(req_id_filter)
        root_logger.addHandler(file_handler)

def get_logger(name: str) -> logging.Logger:
    """各模块获取 logger 的入口"""
    return logging.getLogger(name)
