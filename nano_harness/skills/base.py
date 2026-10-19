"""
Skill 基类
==========
所有 Skill 的基类，定义 Skill 的标准接口。
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


class BaseSkill(ABC):
    """
    Skill 基类
    
    子类必须实现：
    - name: Skill 名称
    - description: Skill 描述
    - get_tools(): 返回工具列表
    """
    
    # 子类必须覆盖的类属性 (不可变)
    name: str = ""
    description: str = ""
    
    # 可选元数据 (不可变)
    version: str = "0.1.0"
    author: str = ""
    category: str = "general"

    def __init_subclass__(cls, **kwargs):
        """
        [极客技巧] 子类定义时自动校验。
        如果子类忘记写 name，在 import 阶段就会直接报错（Fail Fast）。
        """
        super().__init_subclass__(**kwargs)
        if not cls.name:
            raise ValueError(f"Skill 子类 {cls.__name__} 必须定义非空的 `name` 属性！")
        if not cls.description:
            raise ValueError(f"Skill 子类 {cls.__name__} 必须定义非空的 `description` 属性！")

    def __init__(self):
        # 将可变容器和实例状态绑定到 self，避免所有子类共享同一个列表
        self.tags: list[str] = []
        self.dependencies: list[str] = []
        self._initialized: bool = False
        
        # 缓存工具数量，避免 get_metadata 频繁调用 get_tools 导致的性能问题
        self._cached_tool_count: int | None = None

    @abstractmethod
    def get_tools(self) -> list[BaseTool]:
        """
        返回该 Skill 提供的所有工具
        """
        ...

    def initialize(self, context: dict | None = None):
        """
        初始化钩子 - Skill 被加载时调用
        可以在这里加载模型、建立连接等。
        """
        self._initialized = True
        logger.debug(f"[Skill] 初始化完成: {self.name}")

    def cleanup(self):
        """
        清理钩子 - Skill 被卸载时调用
        可以在这里关闭连接、释放资源等。
        """
        self._initialized = False
        self._cached_tool_count = None
        logger.debug(f"[Skill] 清理完成: {self.name}")

    @property
    def is_initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized

    def get_metadata(self) -> dict[str, Any]:
        """获取 Skill 元数据"""
        # 延迟计算并缓存 tool_count，防止每次查元数据都重建一次 tools
        if self._cached_tool_count is None:
            try:
                self._cached_tool_count = len(self.get_tools())
            except Exception as e:
                logger.warning(f"[Skill] {self.name} 获取工具数量失败: {e}")
                self._cached_tool_count = 0

        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "category": self.category,
            "tags": self.tags,
            "dependencies": self.dependencies,
            "tool_count": self._cached_tool_count,
        }

    def __repr__(self) -> str:
        return f"<Skill {self.name} v{self.version}>"
