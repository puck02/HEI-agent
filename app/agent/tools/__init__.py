"""Agent tools package — exports all tool functions and the TOOL_REGISTRY list."""

from __future__ import annotations

from app.agent.tools.knowledge import search_health, search_medication, search_tcm
from app.agent.tools.medication import (
    add_medication,
    get_my_medications,
    remove_medication,
    update_medication,
)
from app.agent.tools.health_log import get_health_logs, log_health
from app.agent.tools.memory_tool import search_memory, search_sessions, remember
from app.agent.tools.vision import describe_image

# Tool registry: list of {name, func, description, parameters, is_write}
TOOL_REGISTRY = [
    # ── Read tools (parallel) ──────────────────────────
    {
        "name": "search_health",
        "func": search_health,
        "description": "Search health knowledge base for relevant information",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query for health knowledge"}
            },
            "required": ["query"],
        },
        "is_write": False,
    },
    {
        "name": "search_medication",
        "func": search_medication,
        "description": "Search medication knowledge base for drug information",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query for medication knowledge"}
            },
            "required": ["query"],
        },
        "is_write": False,
    },
    {
        "name": "search_tcm",
        "func": search_tcm,
        "description": "Search Traditional Chinese Medicine knowledge base",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query for TCM knowledge"}
            },
            "required": ["query"],
        },
        "is_write": False,
    },
    {
        "name": "search_memory",
        "func": search_memory,
        "description": "Search user's long-term memories by keywords. LLM decides what keywords to use (e.g., '青霉素 过敏'). Uses SQLite LIKE matching.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The user's ID"},
                "keywords": {"type": "string", "description": "Space-separated keywords to search, e.g. '青霉素 过敏'"}
            },
            "required": ["user_id", "keywords"],
        },
        "is_write": False,
    },
    {
        "name": "search_sessions",
        "func": search_sessions,
        "description": "Search past conversation session summaries by keywords. Useful when the user references previous conversations.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The user's ID"},
                "keywords": {"type": "string", "description": "Space-separated keywords to search past sessions"}
            },
            "required": ["user_id", "keywords"],
        },
        "is_write": False,
    },
    {
        "name": "describe_image",
        "func": describe_image,
        "description": "Describe the content of an image using AI vision",
        "parameters": {
            "type": "object",
            "properties": {
                "image_url": {"type": "string", "description": "URL of the image to describe"}
            },
            "required": ["image_url"],
        },
        "is_write": False,
    },
    {
        "name": "get_my_medications",
        "func": get_my_medications,
        "description": "Get the user's current medication list",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The user's ID"}
            },
            "required": ["user_id"],
        },
        "is_write": False,
    },
    {
        "name": "get_health_logs",
        "func": get_health_logs,
        "description": "Get the user's recent health logs",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The user's ID"},
                "days": {"type": "integer", "description": "Number of days to look back (default 7)"}
            },
            "required": ["user_id"],
        },
        "is_write": False,
    },
    # ── Write tools (serial + confirmation) ────────────
    {
        "name": "add_medication",
        "func": add_medication,
        "description": "Add a new medication for the user (requires confirmation)",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The user's ID"},
                "name": {"type": "string", "description": "Medication name"},
                "dosage": {"type": "string", "description": "Dosage (e.g., 500mg)"},
                "frequency": {"type": "string", "description": "Frequency (e.g., 3 times daily)"},
                "notes": {"type": "string", "description": "Additional notes"}
            },
            "required": ["user_id", "name"],
        },
        "is_write": True,
    },
    {
        "name": "update_medication",
        "func": update_medication,
        "description": "Update an existing medication (requires confirmation)",
        "parameters": {
            "type": "object",
            "properties": {
                "med_id": {"type": "integer", "description": "Medication ID to update"},
                "name": {"type": "string", "description": "New name"},
                "dosage": {"type": "string", "description": "New dosage"},
                "frequency": {"type": "string", "description": "New frequency"},
                "notes": {"type": "string", "description": "New notes"}
            },
            "required": ["med_id"],
        },
        "is_write": True,
    },
    {
        "name": "remove_medication",
        "func": remove_medication,
        "description": "Remove a medication (requires confirmation)",
        "parameters": {
            "type": "object",
            "properties": {
                "med_id": {"type": "integer", "description": "Medication ID to remove"}
            },
            "required": ["med_id"],
        },
        "is_write": True,
    },
    {
        "name": "log_health",
        "func": log_health,
        "description": "Log a health entry for the user (requires confirmation)",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The user's ID"},
                "entry_date": {"type": "string", "description": "Date of the entry (YYYY-MM-DD)"},
                "data": {"type": "string", "description": "Health data to log"}
            },
            "required": ["user_id"],
        },
        "is_write": True,
    },
    {
        "name": "remember",
        "func": remember,
        "description": "Store an important fact in the user's long-term memory (requires confirmation)",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The user's ID"},
                "fact": {"type": "string", "description": "The fact to remember"}
            },
            "required": ["user_id", "fact"],
        },
        "is_write": True,
    },
]

__all__ = [
    "search_health", "search_medication", "search_tcm",
    "search_memory", "search_sessions", "remember",
    "describe_image",
    "get_my_medications", "add_medication", "update_medication", "remove_medication",
    "get_health_logs", "log_health",
    "TOOL_REGISTRY",
]
