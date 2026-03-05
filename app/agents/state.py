"""
Shared Agent state definition for all LangGraph agents.

State flows through the LangGraph pipeline:
1. load_context → classify_intent → sub-agent (ReAct) → reflection → synthesize
"""

from __future__ import annotations

import uuid
from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """Shared state flowing through the LangGraph agent graph."""

    # ── Identity ─────────────────────────────────────────
    user_id: str           # UUID as string
    session_id: str        # Conversation session ID

    # ── Input ────────────────────────────────────────────
    messages: list[dict]   # Chat messages [{role, content}]
    user_message: str      # Current user input

    # ── Routing ──────────────────────────────────────────
    current_intent: str    # classified intent: health / medication / insight / general
    selected_agent: str    # which sub-agent to route to

    # ── Context ──────────────────────────────────────────
    health_context: str    # User health data context
    medication_context: str  # Active medications context
    rag_context: str       # Retrieved knowledge from RAG
    memory_context: dict   # Short-term + long-term memory
    tool_outputs: list[str]  # Results from MCP tool calls

    # ── ReAct Intermediate ───────────────────────────────
    react_steps: list[dict]  # ReAct thinking steps [{thought, action, observation}]
    tools_called: list[str]  # Names of tools invoked during ReAct

    # ── Reflection ───────────────────────────────────────
    reflection_passed: bool        # Whether reflection check passed
    reflection_retry_count: int    # Number of reflection retries (max 2)
    reflection_scores: dict        # Detailed scores from reflection

    # ── Output ───────────────────────────────────────────
    response: str          # Final response to user
    model_used: str        # Which LLM model produced the response
    agent_used: str        # Which sub-agent handled the request
