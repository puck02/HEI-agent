"""
Profile service — manages MEMORY.md and USER.md files.

Inspired by Hermes Agent's memory system:
- MEMORY.md  → agent's durable notes, dynamically updated
- USER.md    → static user profile, manually curated

Both files are injected into the system prompt every turn.

MEMORY.md is managed by the `remember` tool — the LLM decides what
facts are important enough to persist across sessions.

USER.md is a simple text file that the user/developer maintains.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Default location: project data directory
DEFAULT_PROFILE_DIR = Path.home() / ".hei-agent" / "profiles"


class ProfileService:
    """Read/write MEMORY.md and USER.md for a given user."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or DEFAULT_PROFILE_DIR

    def _user_dir(self, user_id: str) -> Path:
        d = self.base_dir / user_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _read_file(self, user_id: str, filename: str) -> str:
        path = self._user_dir(user_id) / filename
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def _write_file(self, user_id: str, filename: str, content: str) -> None:
        path = self._user_dir(user_id) / filename
        path.write_text(content, encoding="utf-8")

    def _append_to_file(self, user_id: str, filename: str, line: str) -> None:
        path = self._user_dir(user_id) / filename
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if current and not current.endswith("\n"):
            current += "\n"
        path.write_text(current + line + "\n", encoding="utf-8")

    # ── MEMORY.md (agent notes) ──────────────────────────

    def get_memory(self, user_id: str) -> str:
        """Get MEMORY.md content for a user."""
        return self._read_file(user_id, "MEMORY.md")

    def get_memory_lines(self, user_id: str) -> list[str]:
        """Get MEMORY.md as list of non-empty lines."""
        content = self.get_memory(user_id)
        return [l for l in content.split("\n") if l.strip()]

    def write_memory(self, user_id: str, content: str) -> None:
        """Overwrite MEMORY.md."""
        self._write_file(user_id, "MEMORY.md", content)
        log.info("memory_md_written", user_id=user_id, size=len(content))

    def add_memory_fact(self, user_id: str, fact: str) -> None:
        """Append a fact to MEMORY.md."""
        line = f"- {fact}"
        self._append_to_file(user_id, "MEMORY.md", line)
        log.info("memory_fact_added", user_id=user_id, fact=fact[:80])

    def remove_memory_fact(self, user_id: str, fact_substring: str) -> bool:
        """Remove a line from MEMORY.md containing the given substring."""
        lines = self.get_memory_lines(user_id)
        new_lines = [l for l in lines if fact_substring not in l]
        if len(new_lines) == len(lines):
            return False
        self.write_memory(user_id, "\n".join(new_lines))
        return True

    def compact_memory(self, user_id: str, max_lines: int = 50) -> None:
        """Truncate MEMORY.md to max_lines, keeping most recent."""
        lines = self.get_memory_lines(user_id)
        if len(lines) <= max_lines:
            return
        self.write_memory(user_id, "\n".join(lines[-max_lines:]))
        log.info("memory_compacted", user_id=user_id, from_lines=len(lines), to=max_lines)

    # ── USER.md (user profile) ───────────────────────────

    def get_profile(self, user_id: str) -> str:
        """Get USER.md content for a user."""
        return self._read_file(user_id, "USER.md")

    def write_profile(self, user_id: str, content: str) -> None:
        """Overwrite USER.md."""
        self._write_file(user_id, "USER.md", content)
        log.info("user_md_written", user_id=user_id)

    def get_profile_fields(self, user_id: str) -> dict[str, str]:
        """Parse USER.md as key: value pairs."""
        content = self.get_profile(user_id)
        fields: dict[str, str] = {}
        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, _, value = line.partition(":")
                fields[key.strip()] = value.strip()
        return fields

    # ── Combined context for system prompt ───────────────

    def get_system_context(self, user_id: str) -> str:
        """Return MEMORY.md + USER.md formatted for system prompt injection."""
        parts: list[str] = []

        profile = self.get_profile(user_id)
        if profile.strip():
            parts.append(f"## USER.md (用户档案)\n\n{profile.strip()}")

        memory = self.get_memory(user_id)
        if memory.strip():
            parts.append(f"## MEMORY.md (Agent 笔记)\n\n{memory.strip()}")

        return "\n\n".join(parts) if parts else ""
