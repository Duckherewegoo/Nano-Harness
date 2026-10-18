"""
MCP 服务端
==========
将本地的 Skill 和工具暴露为标准 MCP 服务。
"""

import asyncio
import inspect
import json
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import Field, create_model

logger = logging.getLogger(__name__)

# ===== 数据模型 =====

@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    # 安全性：是否标记为高危工具
    requires_confirmation: bool = False 

@dataclass
class MCPResource:
    uri: str
    name: str
    description: str
    mime_type: str = "text/plain"

@dataclass
class MCPPrompt:
    name: str
    description: str
    # 修复可变默认值陷阱
    arguments: list[dict] = field(default_factory=list)


# ===== 核心服务类 =====

class MCPServer:
    """
    MCP 服务端实现 (生产级)
    """

    def __init__(self, name: str = "nano-harness", version: str = "1.0.0"):
        self.name = name
        self.version = version

        self._tools: dict[str, Callable] = {}
        self._tool_schemas: dict[str, MCPTool] = {}
        self._resources: dict[str, MCPResource] = {}
        self._prompts: dict[str, MCPPrompt] = {}

        self._resource_providers: dict[str, Callable] = {}
        self._prompt_providers: dict[str, Callable] = {}

        # MCP 能力声明
        self._capabilities = {
            "tools": {"listChanged": False},
            "resources": {"listChanged": False},
            "prompts": {"listChanged": False},
            "logging": {},
        }

    # ===== 优雅的注册装饰器 (扩展性拉满) =====

    def tool(self, name: str, description: str, requires_confirmation: bool = False):
        """装饰器注册工具用法: @server.tool("add", "两数相加")"""
        def decorator(func: Callable):
            # 尝试从类型提示自动生成 Schema
            schema = {"type": "object", "properties": {}}
            sig = inspect.signature(func)
            for param_name, param in sig.parameters.items():
                if param_name == "self" or param_name == "kwargs":
                    continue
                prop_type = "string"
                if param.annotation is int:
                    prop_type = "integer"
                elif param.annotation is float:
                    prop_type = "number"
                elif param.annotation is bool:
                    prop_type = "boolean"
                
                schema["properties"][param_name] = {
                    "type": prop_type,
                    "description": f"参数: {param_name}"
                }
                if param.default is inspect.Parameter.empty:
                    schema.setdefault("required", []).append(param_name)

            self.register_tool(name, description, func, schema, requires_confirmation)
            return func
        return decorator

    # ===== 注册机制 =====

    def register_tool(
        self,
        name: str,
        description: str,
        handler: Callable,
        input_schema: dict | None = None,
        requires_confirmation: bool = False
    ):
        self._tools[name] = handler
        if input_schema is None:
            input_schema = {"type": "object", "properties": {"input": {"type": "string"}}}
            
        self._tool_schemas[name] = MCPTool(
            name=name, description=description, 
            input_schema=input_schema, requires_confirmation=requires_confirmation
        )

    def register_resource(self, uri: str, name: str, description: str, content_provider: Callable, mime_type: str = "text/plain"):
        self._resources[uri] = MCPResource(uri=uri, name=name, description=description, mime_type=mime_type)
        self._resource_providers[uri] = content_provider

    def register_prompt(self, name: str, description: str, template_provider: Callable, arguments: list[dict] | None = None):
        self._prompts[name] = MCPPrompt(name=name, description=description, arguments=arguments or [])
        self._prompt_providers[name] = template_provider

    # ===== 协议分发 (通信核心) =====

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """处理 MCP 请求 (同步入口)"""
        method = request.get("method", "")
        params = request.get("params", {})
        request_id = request.get("id")

        try:
            result = self._dispatch(method, params)
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except ValueError as e:
            code = -32602 if "argument" in str(e).lower() else -32601
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": str(e)}}
        except Exception as e:
            logger.error(f"MCP 内部错误: {e}", exc_info=True)
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": str(e)}}

    async def handle_http_request(self, request_body: dict) -> dict:
        """处理 HTTP 请求 (异步入口，用于 FastAPI 挂载)"""
        return await asyncio.to_thread(self.handle_request, request_body)

    def _dispatch(self, method: str, params: dict) -> Any:
        """请求路由分发"""
        routes = {
            "initialize": self._handle_initialize,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tool_call,
            "resources/list": self._handle_resources_list,
            "resources/read": self._handle_resources_read,
            "prompts/list": self._handle_prompts_list,
            "prompts/get": self._handle_prompts_get,
            "ping": lambda p: {}
        }
        if method == "notifications/initialized":
            return {}
        if method not in routes:
            raise ValueError(f"Unknown method: {method}")
        return routes[method](params)

    # ===== 各能力处理器 =====

    def _handle_initialize(self, params: dict) -> dict:
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": self._capabilities,
            "serverInfo": {"name": self.name, "version": self.version},
        }

    def _handle_tools_list(self) -> dict:
        return {"tools": [
            {"name": t.name, "description": t.description, "inputSchema": t.input_schema}
            for t in self._tool_schemas.values()
        ]}

    def _handle_tool_call(self, params: dict) -> dict:
        """调用工具 (核心安全防线)"""
        name = params.get("name", "")
        arguments = params.get("arguments", {})

        if name not in self._tools:
            raise ValueError(f"Tool not found: {name}")

        # 🛡️ 安全防线：检查是否是高危操作，且客户端是否传了确认标识
        tool_meta = self._tool_schemas[name]
        if tool_meta.requires_confirmation and not params.get("user_confirmed", False):
            return {
                "content": [{"type": "text", "text": "⚠️ 拒绝执行：此工具为高危操作，需要显式传递 user_confirmed: true。"}],
                "isError": True
            }

        handler = self._tools[name]
        try:
            # 兼容同步和异步 handler
            if inspect.iscoroutinefunction(handler):
                result = asyncio.run(handler(**arguments))
            else:
                result = handler(**arguments)

            # 格式化返回 (支持图文多模态扩展)
            if isinstance(result, (dict, list)):
                content = [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
            else:
                content = [{"type": "text", "text": str(result)}]

            return {"content": content, "isError": False}

        except Exception as e:
            logger.error(f"Tool call error [{name}]: {e}", exc_info=True)
            return {"content": [{"type": "text", "text": f"Error: {e!s}"}], "isError": True}

    def _handle_resources_read(self, params: dict) -> dict:
        """读取资源 (增加防注入限制)"""
        uri = params.get("uri", "")
        
        # 🛡️ 安全防线：防止路径穿越攻击
        if ".." in uri or uri.startswith("/"):
            raise ValueError("Resource read blocked: Path traversal detected")

        if uri not in self._resource_providers:
            raise ValueError(f"Resource not found: {uri}")

        content = self._resource_providers[uri]()
        return {
            "contents": [{
                "uri": uri, "mimeType": self._resources[uri].mime_type,
                "text": content if isinstance(content, str) else json.dumps(content)
            }]
        }

    def _handle_resources_list(self) -> dict:
        return {"resources": [
            {"uri": r.uri, "name": r.name, "description": r.description, "mimeType": r.mime_type}
            for r in self._resources.values()
        ]}

    def _handle_prompts_list(self) -> dict:
        return {"prompts": [
            {"name": p.name, "description": p.description, "arguments": p.arguments}
            for p in self._prompts.values()
        ]}

    def _handle_prompts_get(self, params: dict) -> dict:
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        if name not in self._prompt_providers:
            raise ValueError(f"Prompt not found: {name}")
        prompt_text = self._prompt_providers[name](**arguments)
        return {
            "description": self._prompts[name].description,
            "messages": [{"role": "user", "content": {"type": "text", "text": prompt_text}}],
        }

    # ===== 传输层：标准输入输出通信 =====

    def run_stdio(self):
        """以 stdio 模式运行 (STDIN 读，STDOUT 写)"""
        logger.info("MCP Server starting via stdio...")
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                response = self.handle_request(request)
                # 通信严谨：确保输出是一个单行 JSON，防止破坏管道
                print(json.dumps(response, ensure_ascii=False), flush=True)
            except json.JSONDecodeError:
                logger.warning(f"收到无效的 JSON: {line}")
                continue
            except Exception as e:
                logger.error(f"处理请求时崩溃: {e}")
                # 就算崩溃也要回传错误，而不是让通信死寂
                try:
                    err_resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(e)}}
                    print(json.dumps(err_resp), flush=True)
                except Exception:
                    pass

    # ===== 集成：转 LangChain Tools =====

    def get_tools_for_langchain(self) -> list:
        """将 MCP 工具无缝转换为 LangChain StructuredTool"""
        from langchain_core.tools import StructuredTool

        tools = []
        for name, tool in self._tool_schemas.items():
            handler = self._tools[name]

            # 动态构建 Pydantic 模型
            props = tool.input_schema.get("properties", {})
            required = tool.input_schema.get("required", [])
            
            fields = {}
            for prop_name, prop_info in props.items():
                prop_type = str
                if prop_info.get("type") == "integer":
                    prop_type = int
                elif prop_info.get("type") == "number":
                    prop_type = float
                elif prop_info.get("type") == "boolean":
                    prop_type = bool

                default_val = ... if prop_name in required else prop_info.get("default", None)
                fields[prop_name] = (prop_type, Field(default=default_val, description=prop_info.get("description", "")))

            InputModel = create_model(f"{name}_input", **fields)

            tools.append(
                StructuredTool.from_function(
                    func=handler,
                    name=name,
                    description=tool.description,
                    args_schema=InputModel,
                )
            )
        return tools
