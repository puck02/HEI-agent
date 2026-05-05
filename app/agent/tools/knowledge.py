from __future__ import annotations

import logging

log = logging.getLogger(__name__)

try:
    from app.services.knowledge_service import KnowledgeService
except ImportError:
    KnowledgeService = None
    log.warning("knowledge_service_unavailable")


async def search_health(query: str) -> str:
    if KnowledgeService is None:
        return "knowledge service unavailable"
    try:
        results = await KnowledgeService.search_health(query)
        if not results:
            return f"No health knowledge results found for: {query}"
        formatted = "\n".join(
            f"- {r.get('content', str(r))}" for r in results
        )
        return f"Health knowledge for \"{query}\":\n{formatted}"
    except Exception:
        log.exception("search_health_failed query=%s", query[:100])
        return "knowledge service unavailable"


async def search_medication(query: str) -> str:
    if KnowledgeService is None:
        return "knowledge service unavailable"
    try:
        results = await KnowledgeService.search_medication(query)
        if not results:
            return f"No medication knowledge results found for: {query}"
        formatted = "\n".join(
            f"- {r.get('content', str(r))}" for r in results
        )
        return f"Medication knowledge for \"{query}\":\n{formatted}"
    except Exception:
        log.exception("search_medication_failed query=%s", query[:100])
        return "knowledge service unavailable"


async def search_tcm(query: str) -> str:
    if KnowledgeService is None:
        return "knowledge service unavailable"
    try:
        results = await KnowledgeService.search_tcm(query)
        # Fallback: if tcm_wellness returns fewer than 2 results, cross-search health_knowledge
        if not results or len(results) < 2:
            health_results = await KnowledgeService.search_health(query)
            if health_results:
                # Merge results, deduplicate by content
                seen = {r.get('content', str(r)) for r in results}
                for hr in health_results:
                    if hr.get('content', str(hr)) not in seen:
                        results.append(hr)
                # Sort by score if available
                results = sorted(
                    results,
                    key=lambda r: r.get('score', r.get('relevance_score', 0.0)),
                    reverse=True,
                )[:5]
        if not results:
            return f"No TCM or health knowledge results found for: {query}"
        formatted = "\n".join(
            f"- {r.get('content', str(r))}" for r in results
        )
        return f"TCM & Health knowledge for \"{query}\":\n{formatted}"
    except Exception:
        log.exception("search_tcm_failed query=%s", query[:100])
        return "knowledge service unavailable"
