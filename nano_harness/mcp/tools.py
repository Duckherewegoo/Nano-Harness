"""
MCP 工具适配器
==============
将本地 Skill 和工具适配为 MCP 格式的桥接层。
"""

from collections.abc import Callable
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import Field, create_model

from ..utils.logger_setup import get_logger
from .client import MCPClient
from .server import MCPServer

logger = get_logger(__name__)


class MCPToolAdapter:
    """
    MCP 工具适配器
    负责在 MCP 协议和本地工具系统之间做双向转换。
    """

    def __init__(self, namespace: str = "nano"):
        self.namespace = namespace

    # ===== LangChain → MCP =====

    def langchain_to_mcp(self, tool: BaseTool) -> dict[str, Any]:
        """将 LangChain 工具转换为 MCP 工具定义"""
        name = f"{self.namespace}_{tool.name}"
        description = tool.description
        input_schema = self._extract_schema(tool)

        # 严谨鲁棒：兼容同步和异步 LangChain 工具
        def handler(**kwargs):
            # 如果是异步工具，MCP Server 那边会处理 await，这里直接调用即可
            return tool.invoke(kwargs)

        return {
            "name": name,
            "description": description,
            "input_schema": input_schema,
            "handler": handler,
        }

    def _extract_schema(self, tool: BaseTool) -> dict[str, Any]:
        """从 LangChain 工具提取输入参数的 JSON Schema"""
        try:
            if hasattr(tool, "args_schema") and tool.args_schema:
                if hasattr(tool.args_schema, "model_json_schema"):  # Pydantic v2
                    schema = tool.args_schema.model_json_schema()
                else:
                    schema = tool.args_schema.schema()  # Pydantic v1 兼容
                schema.pop("title", None)
                return schema
        except Exception as e:
            logger.warning("提取工具 %s 的 Schema 失败: %s", tool.name, e)

        # 默认 Schema
        return {
            "type": "object",
            "properties": {"input": {"type": "string", "description": "输入参数"}},
        }

    def register_skill_to_mcp(self, skill: Any, server: MCPServer):
        """将一个 Skill 的所有工具注册到 MCP 服务端"""
        tools = skill.get_tools()
        for tool in tools:
            if not isinstance(tool, BaseTool):
                logger.warning("跳过非法的工具类型: %s", type(tool))
                continue

            mcp_tool = self.langchain_to_mcp(tool)
            server.register_tool(
                name=mcp_tool["name"],
                description=mcp_tool["description"],
                handler=mcp_tool["handler"],
                input_schema=mcp_tool["input_schema"],
            )
            logger.info("已注册 Skill 工具到 MCP: %s", mcp_tool["name"])

    # ===== MCP → LangChain =====

    def mcp_to_langchain_tool(
        self,
        name: str,
        description: str,
        handler: Callable,
        input_schema: dict[str, Any] | None = None, # 必须接收 Schema
    ) -> BaseTool:
        """
        将 MCP 工具转换为 LangChain 工具。
        核心：必须把 JSON Schema 转成 Pydantic Model 传给 LangChain。
        """
        # 动态构建 Pydantic 模型
        if input_schema and "properties" in input_schema:
            props = input_schema["properties"]
            required = input_schema.get("required", [])
            
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

            args_schema = create_model(f"{name}_input", **fields)
        else:
            args_schema = None

        return StructuredTool.from_function(
            func=handler,
            name=name,
            description=description,
            args_schema=args_schema,
        )

    def import_mcp_tools(
        self,
        client: MCPClient,
        skill_registry: Any = None,
    ) -> list[BaseTool]:
        """从远程 MCP 服务导入所有工具"""
        remote_tools = client.list_tools()
        langchain_tools = []

        for tool_info in remote_tools:
            # 优雅的闭包捕获
            def tool_call(tool_name=tool_info.name, **kwargs):
                try:
                    return client.call_tool(tool_name, kwargs)
                except Exception as e:
                    logger.error("调用远程工具 %s 失败: %s", tool_name, e)
                    return f"Error: {e!s}"

            # 假设 tool_info 带有 inputSchema 属性，透传给转换器
            tool = self.mcp_to_langchain_tool(
                name=f"mcp_{client.service_name}_{tool_info.name}",
                description=f"[来自 MCP {client.service_name}] {tool_info.description}",
                handler=tool_call,
                input_schema=getattr(tool_info, "input_schema", None),
            )
            langchain_tools.append(tool)

        # 如果有 Skill 注册中心，包装为虚拟 Skill
        if skill_registry:
            class RemoteMCPSkill:
                name = f"mcp_{client.service_name}"
                description = f"远程 MCP 服务: {client.service_name}"

                def get_tools(self_inner): # 避免名称冲突
                    return langchain_tools

            skill_registry.register(RemoteMCPSkill())
            logger.info("已导入 %d 个远程工具到 Skill 注册中心", len(langchain_tools))

        return langchain_tools

    # ===== 服务端创建 =====

    def create_server_from_skills(
        self,
        skills: list,
        name: str = "nano-harness-mcp",
    ) -> MCPServer:
        """从一组 Skill 创建 MCP 服务端"""
        server = MCPServer(name=name)
        for skill in skills:
            self.register_skill_to_mcp(skill, server)
        return server
