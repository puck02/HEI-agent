"""
MCP Server — registers all tools and exposes them via SSE transport.

The Agent layer connects to this server as an MCP client,
converting MCP tools to LangChain-compatible tools via langchain-mcp-adapters.
"""

from __future__ import annotations

import structlog
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, Tool

from app.mcp.tools.calculator import calculate
from app.mcp.tools.health_data_query import query_health_data
from app.mcp.tools.weather import get_weather
from app.mcp.tools.web_search import web_search

log = structlog.get_logger(__name__)

# MCP Server instance
mcp_server = Server("hel-agent-tools")


# ── Tool Registration ────────────────────────────────────


@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="calculator",
            description="执行数学计算，包括 BMI 计算、药物剂量换算、营养摄入计算等。输入数学表达式或描述。",
            inputSchema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式，如 '70/(1.75**2)' 或 '2+3*4'",
                    }
                },
                "required": ["expression"],
            },
        ),
        Tool(
            name="weather",
            description="获取指定城市的天气信息（温度、湿度、空气质量），用于分析环境因素对健康的影响。",
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称，如 '北京'、'上海'",
                    }
                },
                "required": ["city"],
            },
        ),
        Tool(
            name="web_search",
            description="在互联网上搜索健康相关信息。仅用于补充知识库中不足的健康知识。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询词",
                    }
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="health_data_query",
            description="查询用户的历史健康数据。可按日期范围、指标类型查询。",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户 ID"},
                    "metric": {
                        "type": "string",
                        "description": "指标类型：headache/neck_shoulder/stomach/nose_throat/knee/mood/sleep/steps",
                    },
                    "days": {
                        "type": "integer",
                        "description": "查询最近 N 天的数据",
                        "default": 7,
                    },
                },
                "required": ["user_id"],
            },
        ),
    ]


@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "calculator":
            result = calculate(arguments["expression"])
        elif name == "weather":
            result = await get_weather(arguments["city"])
        elif name == "web_search":
            result = await web_search(arguments["query"])
        elif name == "health_data_query":
            result = await query_health_data(
                user_id=arguments["user_id"],
                metric=arguments.get("metric"),
                days=arguments.get("days", 7),
            )
        else:
            result = f"未知工具: {name}"

        return [TextContent(type="text", text=str(result))]
    except Exception as e:
        log.error("mcp_tool_error", tool=name, error=str(e))
        return [TextContent(type="text", text=f"工具执行失败: {e}")]


# ── SSE Transport for FastAPI integration ────────────────

sse_transport = SseServerTransport("/mcp/sse")


def get_mcp_server() -> Server:
    return mcp_server
