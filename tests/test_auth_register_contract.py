from app.auth.schemas import RegisterRequest


def test_register_request_requires_email():
    payload = {
        "username": "tester_01",
        "password": "secret123",
        "display_name": "Tester",
    }

    try:
        RegisterRequest(**payload)
        assert False, "RegisterRequest should require email"
    except Exception as exc:
        assert "email" in str(exc).lower()
