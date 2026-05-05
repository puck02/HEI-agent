from __future__ import annotations

import logging

from app.services.medication_service import MedicationService

log = logging.getLogger(__name__)


async def get_my_medications(user_id: str) -> str:
    service = MedicationService()
    try:
        records = service.get_all(user_id)
        if not records:
            return "No medications on file."
        lines = [f"- {r['name']} ({r.get('dosage', '')} {r.get('frequency', '')}) — {r.get('notes', '')}" for r in records]
        return "Your medications:\n" + "\n".join(lines)
    except Exception:
        log.exception("get_my_medications_failed user_id=%s", user_id)
        return "Failed to retrieve medications."


async def add_medication(
    user_id: str,
    name: str,
    dosage: str = "",
    frequency: str = "",
    notes: str = "",
) -> str:
    service = MedicationService()
    try:
        med_id = service.add(user_id, {
            "name": name,
            "dosage": dosage,
            "frequency": frequency,
            "notes": notes,
        })
        return f"Medication \"{name}\" added (id={med_id})."
    except Exception:
        log.exception("add_medication_failed user_id=%s name=%s", user_id, name)
        return "Failed to add medication."


async def update_medication(
    med_id: int,
    name: str = "",
    dosage: str = "",
    frequency: str = "",
    notes: str = "",
) -> str:
    service = MedicationService()
    try:
        ok = service.update(med_id, {
            "name": name,
            "dosage": dosage,
            "frequency": frequency,
            "notes": notes,
        })
        if ok:
            return f"Medication {med_id} updated."
        return f"Medication {med_id} not found."
    except Exception:
        log.exception("update_medication_failed med_id=%s", med_id)
        return "Failed to update medication."


async def remove_medication(med_id: int) -> str:
    service = MedicationService()
    try:
        ok = service.remove(med_id)
        if ok:
            return f"Medication {med_id} removed."
        return f"Medication {med_id} not found."
    except Exception:
        log.exception("remove_medication_failed med_id=%s", med_id)
        return "Failed to remove medication."
