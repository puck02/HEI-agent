from app.auth.router import router
from app.auth.schemas import TokenResponse


def test_register_route_returns_token_response_model():
    register_route = next(r for r in router.routes if getattr(r, "path", "") == "/auth/register")
    assert register_route.response_model is TokenResponse
