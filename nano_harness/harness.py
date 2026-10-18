"""
Harness 核心编排引擎
====================
这是整个系统的"驾驭"大脑，负责任务拆解、智能体调度、状态管理、结果汇总。
"""

import inspect
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from .agent.base import BaseAgent
from .agent.coordinator import CoordinatorAgent
from .agent.critic import CriticAgent
from .agent.executor import ExecutorAgent
from .agent.planner import PlannerAgent
from .prompts.optimizer import PromptOptimizer
from .prompts.templates import PromptTemplateEngine
from .skills.registry import SkillRegistry
from .utils.logger_setup import get_logger

logger = get_logger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    CRITIQUING = "critiquing"
    WAITING_USER = "waiting_user"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskContext:
    task_id: str
    query: str
    status: TaskStatus = TaskStatus.PENDING
    messages: list[BaseMessage] = field(default_factory=list)
    plan: dict | None = None
    execution_results: list[dict] = field(default_factory=list)
    critique: str | None = None
    final_result: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    user_decisions: list[dict] = field(default_factory=list)
    iteration_count: int = 0
    max_iterations: int = 5


@dataclass
class HarnessConfig:
    max_iterations: int = 5
    enable_critique: bool = True
    enable_human_in_the_loop: bool = True
    auto_load_skills: bool = True
    default_model: str = "gpt-4o"


class Harness:
    """NanoHarness 核心编排器"""

    def __init__(
        self,
        llm: BaseChatModel,
        config: HarnessConfig | None = None,
        skill_registry: SkillRegistry | None = None,
        user_confirm_callback: Callable | None = None,
    ):
        self.llm = llm
        self.config = config or HarnessConfig()
        self.skill_registry = skill_registry or SkillRegistry()
        self.user_confirm_callback = user_confirm_callback or self._default_confirm

        self.prompt_engine = PromptTemplateEngine()
        self.prompt_optimizer = PromptOptimizer()

        self.agents: dict[str, BaseAgent] = {}
        self._init_agents()

        self._tasks: dict[str, TaskContext] = {}

    def _init_agents(self):
        agent_kwargs = {
            "llm": self.llm,
            "prompt_engine": self.prompt_engine,
            "skill_registry": self.skill_registry,
        }
        self.agents["coordinator"] = CoordinatorAgent(**agent_kwargs)
        self.agents["planner"] = PlannerAgent(**agent_kwargs)
        self.agents["executor"] = ExecutorAgent(**agent_kwargs)
        self.agents["critic"] = CriticAgent(**agent_kwargs)

    def create_task(self, query: str, **metadata) -> TaskContext:
        task_id = str(uuid.uuid4())[:8]
        task = TaskContext(
            task_id=task_id,
            query=query,
            messages=[HumanMessage(content=query)],
            metadata=metadata,
            max_iterations=self.config.max_iterations,
        )
        self._tasks[task_id] = task
        logger.info("创建新任务 [%s]: %s", task_id, query[:50])
        return task

    async def run(self, query: str, **metadata) -> str:
        """执行一个完整任务"""
        task = self.create_task(query, **metadata)
        
        try:
            # 主循环 - 反思迭代机制
            while task.iteration_count < task.max_iterations:
                task.iteration_count += 1
                
                # 阶段1：规划
                task.status = TaskStatus.PLANNING
                logger.info("任务 [%s] 第 %d 轮 - 规划中", task.task_id, task.iteration_count)
                task.plan = await self.agents["planner"].plan(task)
                
                # 阶段2：执行
                task.status = TaskStatus.EXECUTING
                logger.info("任务 [%s] 第 %d 轮 - 执行中", task.task_id, task.iteration_count)
                results = await self.agents["executor"].execute(task)
                task.execution_results.extend(results)
                
                # 检查人机交互
                if self.config.enable_human_in_the_loop:
                    need_confirm = self._check_need_user_confirmation(task)
                    if need_confirm:
                        task.status = TaskStatus.WAITING_USER
                        user_decision = await self._ask_user_confirmation(task, need_confirm)
                        task.user_decisions.append(user_decision)
                        if not user_decision.get("approved", True):
                            logger.warning("任务 [%s] 用户否决了高风险操作，重新规划", task.task_id)
                            continue
                
                # 阶段3：评审
                if self.config.enable_critique:
                    task.status = TaskStatus.CRITIQUING
                    logger.info("任务 [%s] 第 %d 轮 - 评审中", task.task_id, task.iteration_count)
                    critique_result = await self.agents["critic"].critique(task)
                    task.critique = critique_result.get("feedback")
                    
                    if critique_result.get("needs_revision", False):
                        logger.info("任务 [%s] 评审未通过，准备下一轮", task.task_id)
                        task.messages.append(AIMessage(
                            content=f"[第{task.iteration_count}轮评审] 需要改进：{critique_result['feedback']}"
                        ))
                        continue
                
                # 达标，退出循环
                break
            
            # 严谨鲁棒：区分是“达标退出”还是“次数耗尽”
            if task.iteration_count >= task.max_iterations and (task.critique and "需要改进" in task.critique):
                logger.warning("任务 [%s] 达到最大迭代次数，且未达标", task.task_id)
                task.status = TaskStatus.FAILED
            else:
                task.status = TaskStatus.COMPLETED
                
            final_result = await self.agents["coordinator"].summarize(task)
            task.final_result = final_result
            return final_result

        except Exception as e:
            # 严谨鲁棒：捕捉所有执行异常，防止服务崩溃
            task.status = TaskStatus.FAILED
            logger.error("任务 [%s] 执行异常: %s", task.task_id, e, exc_info=True)
            raise
        finally:
            # 严谨鲁棒：无论成功失败，都要清理内存中的任务上下文，防止内存泄漏
            # （如果外部需要查询历史，应该在此处将 task 持久化到 Redis/DB，这里为了克制直接 pop）
            self._tasks.pop(task.task_id, None)

    def _check_need_user_confirmation(self, task: TaskContext) -> dict | None:
        """检查是否需要用户确认"""
        for result in task.execution_results[-3:]:
            if result.get("risk_level") == "high":
                return {
                    "reason": "检测到高风险操作",
                    "operation": result.get("tool", "unknown"),
                    "preview": str(result.get("result", ""))[:200],
                }
            if result.get("tool") == "bash" and result.get("needs_confirm", True):
                return {
                    "reason": "Bash命令执行需要确认",
                    "operation": result.get("command", ""),
                    "preview": result.get("description", ""),
                }
        return None
    
    async def _ask_user_confirmation(self, task: TaskContext, reason: dict) -> dict:
        """询问用户确认（兼容同步与异步回调）"""
        try:
            # 严谨鲁棒：判断回调是协程还是同步函数
            if inspect.iscoroutinefunction(self.user_confirm_callback):
                result = await self.user_confirm_callback(task, reason)
            else:
                result = self.user_confirm_callback(task, reason)
            return result if isinstance(result, dict) else {"approved": bool(result)}
        except Exception as e:
            logger.error("用户确认回调失败，默认拒绝: %s", e)
            return {"approved": False, "reason": f"确认异常: {e}"}

    async def _default_confirm(self, task: TaskContext, reason: dict) -> bool:
        """默认确认回调 - 改为 async，防止 await 报错"""
        logger.warning("默认放行高风险操作：%s", reason.get('operation'))
        # 在实际 CLI 中，可以在这里用 input()，但在 Web 中应该返回 False 兜底
        return True 

    def get_task(self, task_id: str) -> TaskContext | None:
        return self._tasks.get(task_id)
    
    def register_skill(self, skill: Any) -> None:  # 加类型提示
        """注册Skill - 动态扩展能力"""
        self.skill_registry.register(skill)
        for agent in self.agents.values():
            agent.refresh_tools()
        logger.info("已注册 Skill: %s", getattr(skill, 'name', 'unknown'))
    
    def optimize_prompt(self, prompt: str, task_type: str = "general") -> str:
        return self.prompt_optimizer.optimize(prompt, task_type)
