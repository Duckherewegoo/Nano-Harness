"""
Skill 基类
==========
所有 Skill 的基类，定义 Skill 的标准接口。
"""

from abc import ABC, abstractmethod
from typing import Any

from langchain_core.tools import BaseTool


class BaseSkill(ABC):
    """
    Skill 基类
    
    子类必须实现：
    - name: Skill 名称
    - description: Skill 描述
    - get_tools(): 返回工具列表
    """
    
    # 子类必须覆盖的类属性 (不可变)
    name: str = "base_skill"
    description: str = "基础 Skill"
    
    # 可选元数据 (不可变)
    version: str = "0.1.0"
    author: str = ""
    category: str = "general"

    def __init__(self):
        # 将可变容器和实例状态绑定到 self，避免所有子类共享同一个列表
        self.tags: list[str] = []
        self.dependencies: list[str] = []
        self._initialized: bool = False

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

    def cleanup(self):
        """
        清理钩子 - Skill 被卸载时调用
        可以在这里关闭连接、释放资源等。
        """
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized

    def get_metadata(self) -> dict[str, Any]:
        """获取 Skill 元数据"""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "category": self.category,
            "tags": self.tags,
            "dependencies": self.dependencies,
            # 注意：如果子类的 get_tools 开销很大，这里可能引发性能问题
            "tool_count": len(self.get_tools()),
        }

    def __repr__(self) -> str:
        return f"<Skill {self.name} v{self.version}>"
