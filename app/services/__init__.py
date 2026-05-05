"""Service layer for HEI-agent."""

from app.services.medication_service import MedicationService
from app.services.health_log_service import HealthLogService

try:
    from app.services.knowledge_service import KnowledgeService
except ImportError:
    KnowledgeService = None

try:
    from app.services.memory_service import MemoryService
except ImportError:
    MemoryService = None

__all__ = [
    "MedicationService",
    "HealthLogService",
    "KnowledgeService",
    "MemoryService",
]
