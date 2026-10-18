"""
REST API 服务端
===============
基于 FastAPI 的 REST API 服务。
"""

import asyncio
import uuid
from asyncio import Lock, TimeoutError, to_thread, wait_for
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# 引入自定义的 logger 和 Request ID 工具
from nano_harness.utils.logger_setup import get_logger, set_req_id

logger = get_logger(__name__)

# 任务超时配置（秒）
TASK_TIMEOUT = 30.0

# 后台任务引用池（防止被垃圾回收）
_background_tasks: set[asyncio.Task] = set()


# ===== 请求/响应模型 =====

class ChatRequest(BaseModel):
    message: str = Field(..., description="用户消息")
    session_id: str | None = Field(None, description="会话ID")
    stream: bool = Field(False, description="是否流式输出")

class ChatResponse(BaseModel):
    response: str = Field(..., description="AI回复")
    session_id: str = Field(..., description="会话ID")
    task_id: str | None = Field(None, description="任务ID")
    timestamp: str = Field(..., description="时间戳")

class TaskCreateRequest(BaseModel):
    description: str = Field(..., description="任务描述")
    priority: str = Field("normal", description="优先级")

class TaskResponse(BaseModel):
    task_id: str
    description: str
    status: str
    result: str | None
    created_at: str
    updated_at: str

class SkillInfo(BaseModel):
    name: str
    description: str
    version: str
    category: str
    tags: list[str]
    tool_count: int

class MCPToolCallRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


# ===== 核心应用工厂 =====

def create_app(harness=None) -> FastAPI:
    """创建 FastAPI 应用实例"""
    app = FastAPI(
        title="NanoHarness API",
        description="轻量级多智能体编排框架 - REST API",
        version="1.0.0",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注入 Request ID 的 HTTP 中间件
    @app.middleware("http")
    async def add_req_id_middleware(request: Request, call_next):
        # 如果上游带了 X-Request-ID 就用，没有就生成一个 8 位短 ID
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        set_req_id(req_id)
        
        response = await call_next(request)
        # 把 ID 返回到响应头，方便前端或客户端追踪
        response.headers["X-Request-ID"] = req_id
        return response

    # 状态存储与异步锁
    tasks: dict[str, dict] = {}
    sessions: dict[str, dict] = {}
    task_lock = Lock()
    session_lock = Lock()

    # ===== 基础接口 =====

    @app.get("/")
    async def root():
        return {
            "name": "NanoHarness API",
            "version": "1.0.0",
            "endpoints": {
                "chat": "/api/v1/chat",
                "tasks": "/api/v1/tasks",
                "skills": "/api/v1/skills",
                "mcp": "/api/v1/mcp",
            },
        }

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "harness_loaded": harness is not None,
        }

    # ===== 对话接口 =====

    @app.post("/api/v1/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest):
        session_id = request.session_id or str(uuid.uuid4())
        task_id = None
        response_text = ""

        if harness:
            try:
                result = await to_thread(harness.run, request.message)
                response_text = result.get("final_output", str(result))
                task_id = result.get("task_id")
            except Exception as e:
                logger.error("对话接口处理异常: %s", e, exc_info=True)
                response_text = f"处理出错：{e!s}"
        else:
            response_text = f"收到消息：{request.message}\n[提示] 当前为演示模式。"

        async with session_lock:
            sessions[session_id] = {
                "last_message": request.message,
                "last_response": response_text,
                "updated_at": datetime.now().isoformat(),
            }

        return ChatResponse(
            response=response_text,
            session_id=session_id,
            task_id=task_id,
            timestamp=datetime.now().isoformat(),
        )

    # ===== 任务接口 =====

    @app.post("/api/v1/tasks", response_model=TaskResponse)
    async def create_task(request: TaskCreateRequest):
        task_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        task = {
            "task_id": task_id,
            "description": request.description,
            "priority": request.priority,
            "status": "pending",
            "result": None,
            "created_at": now,
            "updated_at": now,
        }

        async with task_lock:
            tasks[task_id] = task

        if harness:
            task_obj = asyncio.create_task(_run_task_async(task_id, task, task_lock, harness))
            _background_tasks.add(task_obj)
            task_obj.add_done_callback(_background_tasks.discard)

        return TaskResponse.model_validate(task)

    async def _run_task_async(task_id: str, task: dict, lock: Lock, harness_instance):
        """异步执行任务的后台逻辑"""
        try:
            async with lock:
                task["status"] = "running"
                task["updated_at"] = datetime.now().isoformat()

            logger.info("任务 %s 开始执行", task_id)
            result = await wait_for(
                to_thread(harness_instance.run, task["description"]),
                timeout=TASK_TIMEOUT
            )
            
            async with lock:
                task["result"] = str(result)
                task["status"] = "completed"
            logger.info("任务 %s 执行完成", task_id)
            
        except TimeoutError:
            async with lock:
                task["result"] = f"任务执行超时（上限{TASK_TIMEOUT}秒）"
                task["status"] = "failed"
            logger.error("任务 %s 执行超时", task_id)
        except Exception as e:
            async with lock:
                task["result"] = f"任务失败：{e!s}"
                task["status"] = "failed"
            logger.error("任务 %s 执行异常: %s", task_id, e, exc_info=True)
        finally:
            async with lock:
                task["updated_at"] = datetime.now().isoformat()

    @app.get("/api/v1/tasks/{task_id}", response_model=TaskResponse)
    async def get_task(task_id: str):
        if task_id not in tasks:
            raise HTTPException(status_code=404, detail="任务不存在")
        return TaskResponse.model_validate(tasks[task_id])

    @app.get("/api/v1/tasks")
    async def list_tasks(status: str | None = None):
        result = list(tasks.values())
        if status:
            result = [t for t in result if t["status"] == status]
        return {"total": len(result), "tasks": result}

    # ===== Skill 接口 =====

    @app.get("/api/v1/skills", response_model=list[SkillInfo])
    async def list_skills():
        if not harness or not hasattr(harness, 'skill_registry'):
            return []
        skills = []
        for skill_name in harness.skill_registry.get_skill_names():
            skill = harness.skill_registry.get_skill(skill_name)
            tools = skill.get_tools() if hasattr(skill, 'get_tools') else []
            skills.append(SkillInfo(
                name=skill.name,
                description=skill.description,
                version=skill.version,
                category=getattr(skill, 'category', 'unknown'),
                tags=getattr(skill, 'tags', []),
                tool_count=len(tools),
            ))
        return skills

    @app.get("/api/v1/skills/{skill_name}")
    async def get_skill(skill_name: str):
        if not harness or not hasattr(harness, 'skill_registry'):
            raise HTTPException(status_code=404, detail="Skill注册中心未配置")
        skill = harness.skill_registry.get_skill(skill_name)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill不存在：{skill_name}")
        tools = skill.get_tools() if hasattr(skill, 'get_tools') else []
        return {
            "name": skill.name,
            "description": skill.description,
            "version": skill.version,
            "author": getattr(skill, 'author', 'unknown'),
            "category": getattr(skill, 'category', 'unknown'),
            "tags": getattr(skill, 'tags', []),
            "tools": [t.name for t in tools],
            "tool_count": len(tools),
        }

    # ===== MCP 接口 =====

    @app.get("/api/v1/mcp/tools")
    async def list_mcp_tools():
        if not harness or not hasattr(harness, 'mcp_server'):
            return {"tools": [], "message": "MCP服务未配置"}
        tools = harness.mcp_server.list_tools()
        return {"tools": tools, "count": len(tools)}

    @app.post("/api/v1/mcp/call")
    async def call_mcp_tool(request: MCPToolCallRequest):
        if not harness or not hasattr(harness, 'mcp_server'):
            raise HTTPException(status_code=503, detail="MCP服务未配置")
        try:
            result = await to_thread(
                harness.mcp_server.call_tool,
                request.tool_name,
                request.arguments,
            )
            return {"tool": request.tool_name, "result": result, "success": True}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    # ===== WebSocket =====

    @app.websocket("/ws/chat")
    async def websocket_chat(websocket: WebSocket):
        await websocket.accept()
        
        # WebSocket 没有 HTTP 中间件，手动生成 Request ID
        session_id = str(uuid.uuid4())
        set_req_id(session_id[:8])
        
        logger.info("WebSocket 连接建立：%s", session_id)

        try:
            while True:
                try:
                    data = await websocket.receive_json()
                except ValueError:
                    await websocket.send_json({"type": "error", "message": "无效的JSON格式"})
                    continue

                message = data.get("message", "")
                await websocket.send_json({"type": "status", "status": "thinking"})

                try:
                    if harness:
                        result = await to_thread(harness.run, message)
                        response = str(result)
                    else:
                        response = f"[演示模式] 收到：{message}"
                except Exception as e:
                    response = f"错误：{e!s}"
                    logger.error("WebSocket 消息处理异常: %s", e, exc_info=True)

                await websocket.send_json({
                    "type": "message",
                    "content": response,
                    "session_id": session_id,
                    "timestamp": datetime.now().isoformat(),
                })
        except WebSocketDisconnect:
            logger.info("WebSocket 连接断开：%s", session_id)
        finally:
            async with session_lock:
                sessions.pop(session_id, None)

    # ===== 静态文件 =====
    current_dir = Path(__file__).absolute().parent
    web_dir = current_dir.parent.parent / "web"
    if web_dir.exists():
        app.mount("/ui", StaticFiles(directory=str(web_dir), html=True), name="web")

    return app


def run_server(harness=None, host: str = "0.0.0.0", port: int = 8000, **kwargs):
    """运行 API 服务器"""
    import uvicorn

    app = create_app(harness)

    logger.info("=========================================")
    logger.info("🚀 NanoHarness API 启动中...")
    logger.info("📡 地址: http://%s:%s", host, port)
    logger.info("📚 文档: http://%s:%s/docs", host, port)
    logger.info("🌐 界面: http://%s:%s/ui", host, port)
    logger.info("=========================================")

    uvicorn.run(app, host=host, port=port, **kwargs)
