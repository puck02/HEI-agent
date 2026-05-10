"""ToolRegistry — manages 12 agent tools with parallel read / serial write dispatch."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger(__name__)


class ToolRegistry:
    """Register tools, provide OpenAI-compatible schemas, and dispatch execution."""

    # Read tools can execute in parallel (no side effects)
    READ_TOOL_NAMES = {
        "search_health", "search_medication", "search_tcm",
        "search_memory", "search_sessions", "describe_image",
        "get_my_medications", "get_health_logs",
    }

    # Write tools must execute serially and need user confirmation
    WRITE_TOOL_NAMES = {
        "add_medication", "update_medication", "remove_medication",
        "log_health", "remember",
    }

    def __init__(self) -> None:
        self._tools: dict[str, dict[str, Any]] = {}
        self._pending_write: dict[str, Any] | None = None

    # ── Registration ────────────────────────────────────────

    def register(
        self,
        name: str,
        func: Any,
        description: str,
        parameters: dict[str, Any],
        is_write: bool = False,
    ) -> None:
        """Register a tool."""
        self._tools[name] = {
            "name": name,
            "func": func,
            "description": description,
            "parameters": parameters,
            "is_write": is_write,
        }

    def register_from_registry(self, tool_list: list[dict[str, Any]]) -> None:
        """Register all tools from a list of tool definitions."""
        for tool in tool_list:
            self.register(
                name=tool["name"],
                func=tool["func"],
                description=tool["description"],
                parameters=tool["parameters"],
                is_write=tool.get("is_write", False),
            )

    # ── Queries ─────────────────────────────────────────────

    def get_tool(self, name: str) -> dict[str, Any] | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def is_write_tool(self, name: str) -> bool:
        """Check if a tool is a write (side-effect) tool."""
        tool = self.get_tool(name)
        return bool(tool and tool.get("is_write"))

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Return OpenAI-compatible tool definitions for LLM function calling."""
        schemas = []
        for name, tool in self._tools.items():
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            })
        return schemas

    # ── Pending Confirmation ────────────────────────────────

    def set_pending(self, tool_name: str, args: dict[str, Any]) -> None:
        """Store a pending write tool call awaiting user confirmation."""
        self._pending_write = {"tool_name": tool_name, "args": args}

    def get_pending(self) -> dict[str, Any] | None:
        """Get the pending write tool call, if any."""
        return self._pending_write

    def clear_pending(self) -> None:
        """Clear the pending write tool call."""
        self._pending_write = None

    # ── Execution ───────────────────────────────────────────

    async def execute_read_tools(
        self, tool_calls: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Execute multiple read tools in parallel using asyncio.gather."""
        if not tool_calls:
            return []

        async def _run_one(tc: dict[str, Any]) -> dict[str, Any]:
            func_info = tc.get("function", {})
            name = func_info.get("name", "")
            args = func_info.get("arguments", {})
            if isinstance(args, str):
                import json
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}

            tool = self.get_tool(name)
            if tool is None:
                return {
                    "tool_call_id": tc.get("id", ""),
                    "role": "tool",
                    "content": f"Unknown tool: {name}",
                }

            try:
                result = await tool["func"](**args)
                return {
                    "tool_call_id": tc.get("id", ""),
                    "role": "tool",
                    "content": str(result),
                }
            except Exception as e:
                log.exception("tool_execution_failed tool=%s", name)
                return {
                    "tool_call_id": tc.get("id", ""),
                    "role": "tool",
                    "content": f"Tool error: {e}",
                }

        tasks = [_run_one(tc) for tc in tool_calls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any uncaught exceptions
        final_results = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                final_results.append({
                    "tool_call_id": tool_calls[i].get("id", ""),
                    "role": "tool",
                    "content": f"Tool error: {r}",
                })
            else:
                final_results.append(r)

        return final_results

    async def execute_write_tool(
        self, tool_call: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a single write tool and return the result."""
        func_info = tool_call.get("function", {})
        name = func_info.get("name", "")
        args = func_info.get("arguments", {})
        if isinstance(args, str):
            import json
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}

        tool = self.get_tool(name)
        if tool is None:
            return {
                "tool_call_id": tool_call.get("id", ""),
                "role": "tool",
                "content": f"Unknown tool: {name}",
            }

        try:
            result = await tool["func"](**args)
            return {
                "tool_call_id": tool_call.get("id", ""),
                "role": "tool",
                "content": str(result),
            }
        except Exception as e:
            log.exception("write_tool_execution_failed tool=%s", name)
            return {
                "tool_call_id": tool_call.get("id", ""),
                "role": "tool",
                "content": f"Tool error: {e}",
            }
