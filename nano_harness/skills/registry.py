"""
Skill 注册中心
==============
管理所有已注册的Skill，提供统一的工具发现和调用接口。
"""

import threading

from langchain_core.tools import BaseTool

from ..utils.logger_setup import get_logger
from .base import BaseSkill

logger = get_logger(__name__)


class SkillRegistry:
    """
    Skill 注册中心
    这是整个系统的能力管理中心，所有 Skill 都在这里注册和管理。
    """

    def __init__(self):
        self._skills: dict[str, BaseSkill] = {}
        self._tool_cache: list[BaseTool] | None = None
        self._cache_dirty: bool = True
        # 严谨鲁棒：引入线程锁，防止并发注册和读取时的竞态条件
        self._lock = threading.RLock()

    # ===== Skill 管理 =====

    def register(self, skill: BaseSkill) -> bool:
        """注册一个 Skill"""
        with self._lock:
            if skill.name in self._skills:
                logger.warning("Skill '%s' 已存在，将被覆盖。", skill.name)

            # 检查依赖
            missing_deps = self._check_dependencies(skill)
            if missing_deps:
                logger.warning("Skill '%s' 缺少依赖: %s", skill.name, missing_deps)

            # 严谨鲁棒：生命周期异常隔离
            if not getattr(skill, "is_initialized", False):
                try:
                    skill.initialize()
                    skill.is_initialized = True
                except Exception as e:
                    logger.error("Skill '%s' 初始化失败，拒绝注册: %s", skill.name, e, exc_info=True)
                    return False

            self._skills[skill.name] = skill
            self._cache_dirty = True
            logger.info("Skill 注册成功: %s", skill.name)
            return True

    def unregister(self, skill_name: str) -> bool:
        """注销一个 Skill"""
        with self._lock:
            if skill_name not in self._skills:
                return False

            skill = self._skills[skill_name]
            
            # 检查依赖
            dependents = self._get_dependents(skill_name)
            if dependents:
                logger.warning("Skill %s 依赖 '%s'，卸载可能导致它们崩溃。", dependents, skill_name)

            # 严谨鲁棒：清理失败不阻断卸载流程
            try:
                skill.cleanup()
            except Exception as e:
                logger.error("Skill '%s' 清理失败: %s", skill_name, e, exc_info=True)

            del self._skills[skill_name]
            self._cache_dirty = True
            logger.info("Skill 已卸载: %s", skill_name)
            return True

    def get_skill(self, name: str) -> BaseSkill | None:
        with self._lock:
            return self._skills.get(name)

    def list_skills(self) -> list[BaseSkill]:
        with self._lock:
            return list(self._skills.values())

    def get_skill_names(self) -> list[str]:
        with self._lock:
            return list(self._skills.keys())

    # ===== 工具管理 =====

    def get_all_tools(self) -> list[BaseTool]:
        """获取所有已注册 Skill 的所有工具"""
        with self._lock:
            if self._cache_dirty or self._tool_cache is None:
                self._rebuild_tool_cache()
            # 返回浅拷贝，防止调用方修改列表结构影响缓存
            return self._tool_cache.copy() if self._tool_cache else []

    def get_tools_by_skill(self, skill_name: str) -> list[BaseTool]:
        with self._lock:
            skill = self._skills.get(skill_name)
            if not skill:
                return []
            return skill.get_tools()

    def get_tool_by_name(self, tool_name: str) -> BaseTool | None:
        for tool in self.get_all_tools():
            if tool.name == tool_name:
                return tool
        return None

    def _rebuild_tool_cache(self):
        """重建工具缓存（调用方必须持有锁）"""
        tools = []
        seen_names: set[str] = set()

        for skill in self._skills.values():
            for tool in skill.get_tools():
                # 严谨鲁棒：重名工具处理
                if tool.name in seen_names:
                    original_name = tool.name
                    new_name = f"{skill.name}_{original_name}"
                    
                    # 避免直接修改 Pydantic 模型引发 ValidationError
                    if hasattr(tool, "model_copy"): # Pydantic v2
                        tool = tool.model_copy(update={"name": new_name})
                    elif hasattr(tool, "copy"):     # Pydantic v1
                        tool = tool.copy(update={"name": new_name})
                    else:
                        tool.name = new_name # 兜底

                    logger.warning("工具名冲突: '%s'，已重命名为 '%s'", original_name, new_name)

                tools.append(tool)
                seen_names.add(tool.name)

        self._tool_cache = tools
        self._cache_dirty = False

    # ===== 筛选与搜索 =====

    def search_skills_by_category(self, category: str) -> list[BaseSkill]:
        with self._lock:
            return [s for s in self._skills.values() if getattr(s, "category", "") == category]

    def search_skills_by_tag(self, tag: str) -> list[BaseSkill]:
        with self._lock:
            return [s for s in self._skills.values() if tag in getattr(s, "tags", [])]

    def search_skills(self, query: str) -> list[BaseSkill]:
        """搜索 Skill（在名称、描述、标签中匹配）"""
        query = query.lower()
        results = []
        with self._lock:
            for skill in self._skills.values():
                if (
                    query in skill.name.lower()
                    or query in getattr(skill, "description", "").lower()
                    or any(query in tag.lower() for tag in getattr(skill, "tags", []))
                ):
                    results.append(skill)
        return results

    # ===== 依赖管理 =====

    def _check_dependencies(self, skill: BaseSkill) -> list[str]:
        """检查 Skill 的依赖是否满足"""
        return [dep for dep in getattr(skill, "dependencies", []) if dep not in self._skills]

    def _get_dependents(self, skill_name: str) -> list[str]:
        """获取依赖于指定 Skill 的所有 Skill 名称"""
        return [
            name for name, skill in self._skills.items() 
            if skill_name in getattr(skill, "dependencies", [])
        ]

    # ===== 统计信息 =====

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "total_skills": len(self._skills),
                "total_tools": len(self.get_all_tools()),
                "categories": list(set(getattr(s, "category", "unknown") for s in self._skills.values())),
                "skills": [s.get_metadata() for s in self._skills.values() if hasattr(s, "get_metadata")],
            }

    def __len__(self) -> int:
        with self._lock:
            return len(self._skills)

    def __contains__(self, name: str) -> bool:
        with self._lock:
            return name in self._skills
