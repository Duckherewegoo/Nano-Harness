"""
Bash Skill
==========
执行 Shell 命令的 Skill，带多层安全防御机制。
"""
import datetime
import os
import re
import subprocess
import threading
from collections.abc import Callable
from typing import Any

from langchain_core.tools import StructuredTool, BaseTool
from pydantic import BaseModel, Field

from ..base import BaseSkill

# ================= 风险与黑名单配置 =================

# 极度危险命令（绝对禁止）
FORBIDDEN_REGEX = re.compile(
    r"(rm\s+-rf\s+/|rm\s+-rf\s+/\*|mkfs|dd\s+if=/dev/zero|:\(\)\s*{\s*:\|:&\s*}\s*;|format\s+c:)",
    re.IGNORECASE
)

# 高风险命令（需用户确认）
HIGH_RISK_REGEX = re.compile(
    r"(rm\s+-[a-z]*[rf]|rmdir|shutdown|reboot|halt|poweroff|fdisk|parted|chmod\s+[0-7]*777|chown\s+-R|apt-get|yum\s+install|dnf\s+install|nmap|masscan|hydra|sudo|su\s|kill\s+-9|pkill|killall|>\s*/etc/|>\s*/var/|export\s+PATH=|curl.*\|\s*bash|wget.*\|\s*sh|openssl\s+enc|drop\s+table|truncate)",
    re.IGNORECASE
)

# ================= 工具参数定义 (Agent 标准) =================

class ExecuteBashInput(BaseModel):
    command: str = Field(..., description="要执行的 Linux Shell 命令，如 'ls -la'。")

class CheckRiskInput(BaseModel):
    command: str = Field(..., description="要评估的 Shell 命令。")

class HistoryInput(BaseModel):
    limit: int = Field(10, description="获取最近的历史记录条数，默认 10。")


# ================= 核心 Skill =================

class BashSkill(BaseSkill):
    """Bash 命令执行 Skill (带企业级安全防护)"""
    
    name = "bash"
    description = "执行 Linux Shell 命令，支持文件操作、系统管理、程序运行等。含有安全拦截机制。"
    version = "1.1.0"
    author = "nano-harness"
    category = "system"
    tags = ["bash", "shell", "linux", "command", "system"]
    
    def __init__(
        self,
        work_dir: str = ".",
        user_confirm_callback: Callable[[str, str], bool] | None = None,
        timeout: int = 30,
        max_output_length: int = 10000,
        auto_confirm_low_risk: bool = True,
    ):
        super().__init__()
        self.work_dir = os.path.abspath(work_dir)
        self.user_confirm_callback = user_confirm_callback
        self.timeout = timeout
        self.max_output_length = max_output_length
        self.auto_confirm_low_risk = auto_confirm_low_risk
        
        # 并发安全保护
        self._history_lock = threading.Lock()
        self._command_history: list[dict] = []
    
    def get_tools(self) -> list[BaseTool]:
        """返回标准化的 LangChain 工具列表"""
        return [
            StructuredTool.from_function(
                func=self._safe_execute_command,
                name="execute_bash",
                description="执行 Linux Shell 命令。危险命令会触发安全拦截或需要用户确认。命令将在受限的工作目录下执行。",
                args_schema=ExecuteBashInput,
            ),
            StructuredTool.from_function(
                func=self._safe_check_risk,
                name="check_command_risk",
                description="评估命令的风险等级（low/medium/high/forbidden），返回是否可执行。",
                args_schema=CheckRiskInput,
            ),
            StructuredTool.from_function(
                func=self._safe_get_history,
                name="get_command_history",
                description="获取最近执行的命令历史记录。",
                args_schema=HistoryInput,
            ),
        ]

    # ================= 安全包装器 =================

    def _safe_execute_command(self, command: str) -> str:
        try:
            return self._execute_command_internal(command)
        except Exception as e:
            return f"❌ 执行异常拦截：{e!s}"

    def _safe_check_risk(self, command: str) -> str:
        try:
            return self._check_risk_internal(command)
        except Exception as e:
            return f"❌ 风险评估异常：{e!s}"

    def _safe_get_history(self, limit: int = 10) -> str:
        try:
            return self._get_history_internal(limit)
        except Exception as e:
            return f"❌ 获取历史异常：{e!s}"

    # ================= 核心业务实现 =================

    def _execute_command_internal(self, command: str) -> str:
        # 1. 绝对禁止命令拦截
        if FORBIDDEN_REGEX.search(command):
            return f"🚫 命令被强行拦截：\n`{command}`\n\n该操作极度危险，系统已自动阻断。"

        # 2. 风险评估
        risk_level = self._assess_risk_internal(command)

        # 3. 用户确认
        if self._needs_confirmation(risk_level):
            if not self.user_confirm_callback:
                return f"⚠️ 风险等级 [{risk_level}]，需人工确认，但当前未配置确认回调函数。已阻断执行。"
            
            try:
                confirmed = self.user_confirm_callback(command, risk_level)
            except Exception as e:
                return f"❌ 用户确认阶段发生异常，已阻断：{e!s}"
            
            if not confirmed:
                return "🛑 用户已拒绝执行该命令。"

        # 4. 执行命令
        start_time = datetime.datetime.now()
        
        try:
            # 使用 shell=True 是必须的，但限制了 cwd
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=self.work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace" # 防止非 UTF-8 字符导致 UnicodeDecodeError
            )
            stdout, stderr = process.communicate(timeout=self.timeout)
            success = process.returncode == 0
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            stdout, stderr, success = "", f"执行超时 (>{self.timeout}秒)", False
        except Exception as e:
            stdout, stderr, success = "", str(e), False

        # 5. 记录历史
        duration = (datetime.datetime.now() - start_time).total_seconds()
        with self._history_lock:
            self._command_history.append({
                "command": command,
                "risk_level": risk_level,
                "success": success,
                "timestamp": start_time.isoformat(),
            })
            if len(self._command_history) > 50:
                self._command_history.pop(0)

        # 6. 截断输出
        if len(stdout) > self.max_output_length:
            stdout = stdout[:self.max_output_length] + f"\n... [输出已截断，共 {len(stdout)} 字符]"
        if len(stderr) > self.max_output_length:
            stderr = stderr[:self.max_output_length] + "\n... [错误输出已截断]"

        # 7. 格式化返回
        lines = [f"$ {command}"]
        if risk_level != "low":
            lines.insert(0, f"⚠️ 已执行 [{risk_level}] 风险命令")
        
        if stdout:
            lines.append(stdout.strip())
        if stderr:
            lines.append("【标准错误】")
            lines.append(stderr.strip())
        if not success:
            lines.append(f"【退出码】{process.returncode if 'process' in locals() else 'Unknown'}")
        
        lines.append(f"【耗时】{duration:.2f}s")
        return "\n".join(lines)

    def _assess_risk_internal(self, command: str) -> str:
        cmd = command.strip()
        if FORBIDDEN_REGEX.search(cmd):
            return "forbidden"
        if HIGH_RISK_REGEX.search(cmd):
            return "high"
        
        # 中风险
        if re.search(r"(mkdir|touch|cp|mv|echo|curl|wget|pip|npm|git|chmod|chown)", cmd):
            return "medium"
        
        # 低风险
        if re.match(r"^(ls|pwd|cat|head|tail|wc|whoami|date|uname|ps|df|du|find|grep)", cmd):
            return "low"
            
        return "medium"

    def _needs_confirmation(self, risk_level: str) -> bool:
        if risk_level == "high":
            return True
        if risk_level == "medium":
            return not self.auto_confirm_low_risk
        return False

    def _check_risk_internal(self, command: str) -> str:
        risk = self._assess_risk_internal(command)
        need = self._needs_confirmation(risk)
        return f"风险等级：{risk.upper()}\n需要确认：{'是' if need else '否'}"

    def _get_history_internal(self, limit: int) -> str:
        with self._history_lock:
            if not self._command_history:
                return "暂无命令历史。"
            recent = self._command_history[-limit:]
        
        lines = ["【最近命令记录】"]
        for cmd in reversed(recent):
            icon = "✅" if cmd["success"] else "❌"
            lines.append(f"{icon} [{cmd['risk_level']}] {cmd['command']}")
        return "\n".join(lines)

    # ================= 生命周期 =================

    def initialize(self, context: dict | None = None):
        super().initialize(context)
        os.makedirs(self.work_dir, exist_ok=True)
