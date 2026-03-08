from app.schemas.medication import MedInfoSummaryResponse, MedNlpParseResponse


def test_medication_response_defaults_are_independent():
    left = MedNlpParseResponse()
    right = MedNlpParseResponse()

    left.mentioned_meds.append({"name": "A", "in_library": True})

    assert right.mentioned_meds == []


def test_med_info_summary_default_candidates():
    response = MedInfoSummaryResponse()
    assert response.name_candidates == []
