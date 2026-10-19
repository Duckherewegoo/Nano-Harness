"""
Skill 机制包
============
可插拔的技能包系统。

Skill 是一组相关工具的集合，代表某一领域的能力。
可以动态注册、加载、卸载，实现能力的热插拔。

设计理念：
- 每个 Skill 是一个独立的能力单元
- Skill 可以包含多个工具
- Skill 有自己的元数据（名称、描述、版本等）
- Skill 可以依赖其他 Skill
- Skill 可以被 MCP 协议暴露
"""

from .base import BaseSkill
from .registry import SkillRegistry, get_registry

__all__ = [
    "BaseSkill",
    "SkillRegistry",
    "get_registry",
]
